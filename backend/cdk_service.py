"""
CDK (Activation Code) Service for CausalGraph platform
Handles CDK validation, activation, and OpenAI API access control
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, Tuple
import aiosqlite
from config import Config

class CDKService:
    """Service for managing CDK activations and OpenAI API access"""
    
    def __init__(self):
        self.config = Config
    
    async def validate_cdk(self, cdk_code: str) -> Tuple[bool, str]:
        """
        Validate a CDK code
        
        Args:
            cdk_code: The CDK code to validate
            
        Returns:
            Tuple[bool, str]: (is_valid, message)
        """
        if not self.config.CDK_ENABLED:
            return False, "CDK system is disabled"
        
        if cdk_code.upper() in [code.upper() for code in self.config.CDK_CODES]:
            return True, "CDK code is valid"
        
        return False, "Invalid CDK code"
    
    async def activate_cdk(self, user_id: str, cdk_code: str, db: aiosqlite.Connection) -> Tuple[bool, str]:
        """
        Activate a CDK for a user
        
        Args:
            user_id: The user ID to activate the CDK for
            cdk_code: The CDK code to activate
            
        Returns:
            Tuple[bool, str]: (success, message)
        """
        # Validate CDK code
        is_valid, message = await self.validate_cdk(cdk_code)
        if not is_valid:
            return False, message
        
        try:
            # Check if user already has an active activation
            cursor = await db.execute(
                "SELECT id FROM cdk_activations WHERE user_id = ? AND is_active = 1",
                (user_id,)
            )
            existing = await cursor.fetchone()
            
            if existing:
                # Update existing activation
                expires_at = datetime.utcnow() + timedelta(days=self.config.CDK_EXPIRY_DAYS)
                await db.execute(
                    "UPDATE cdk_activations SET cdk_code = ?, activated_at = CURRENT_TIMESTAMP, expires_at = ?, is_active = 1 WHERE user_id = ?",
                    (cdk_code.upper(), expires_at, user_id)
                )
            else:
                # Create new activation
                activation_id = str(uuid.uuid4())
                expires_at = datetime.utcnow() + timedelta(days=self.config.CDK_EXPIRY_DAYS)
                await db.execute(
                    "INSERT INTO cdk_activations (id, user_id, cdk_code, activated_at, expires_at, is_active) VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, 1)",
                    (activation_id, user_id, cdk_code.upper(), expires_at)
                )
            
            await db.commit()
            return True, f"CDK activated successfully. Expires on {expires_at.strftime('%Y-%m-%d')}"
            
        except Exception as e:
            await db.rollback()
            return False, f"Error activating CDK: {str(e)}"
    
    async def get_user_cdk_status(self, user_id: str, db: aiosqlite.Connection) -> dict:
        """
        Get the CDK activation status for a user
        
        Args:
            user_id: The user ID to check
            
        Returns:
            dict: CDK status information
        """
        try:
            cursor = await db.execute(
                "SELECT cdk_code, activated_at, expires_at, is_active FROM cdk_activations WHERE user_id = ? AND is_active = 1 ORDER BY activated_at DESC LIMIT 1",
                (user_id,)
            )
            result = await cursor.fetchone()
            
            if not result:
                return {
                    "is_activated": False,
                    "expires_at": None,
                    "remaining_days": None,
                    "cdk_code": None
                }
            
            cdk_code, activated_at, expires_at, is_active = result
            
            if not is_active:
                return {
                    "is_activated": False,
                    "expires_at": None,
                    "remaining_days": None,
                    "cdk_code": None
                }
            
            # Check if expired
            now = datetime.utcnow()
            
            # Convert expires_at to datetime if it's a string
            if isinstance(expires_at, str):
                try:
                    expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                except ValueError:
                    print(f"Error parsing expires_at: {expires_at}")
                    expires_at = None
            
            if expires_at and now > expires_at:
                # Mark as expired
                await db.execute(
                    "UPDATE cdk_activations SET is_active = 0 WHERE user_id = ?",
                    (user_id,)
                )
                await db.commit()
                
                return {
                    "is_activated": False,
                    "expires_at": None,
                    "remaining_days": None,
                    "cdk_code": None
                }
            
            # Calculate remaining days
            remaining_days = None
            if expires_at:
                remaining_days = (expires_at - now).days
            
            return {
                "is_activated": True,
                "expires_at": expires_at.isoformat() if expires_at else None,
                "remaining_days": remaining_days,
                "cdk_code": cdk_code
            }
            
        except Exception as e:
            print(f"Error getting CDK status: {e}")
            return {
                "is_activated": False,
                "expires_at": None,
                "remaining_days": None,
                "cdk_code": None
            }
    
    def can_use_openai(self, cdk_status: dict) -> bool:
        """
        Check if user can use OpenAI API based on CDK status
        
        Args:
            cdk_status: The user's CDK status
            
        Returns:
            bool: True if user can use OpenAI API
        """
        if not self.config.CDK_ENABLED:
            return True  # If CDK is disabled, allow OpenAI usage
        
        return cdk_status.get("is_activated", False)
    
    def get_available_models(self, cdk_status: dict) -> dict:
        """
        Get available models based on CDK status
        
        Args:
            cdk_status: The user's CDK status
            
        Returns:
            dict: Available models configuration
        """
        can_use_openai = self.can_use_openai(cdk_status)
        
        models = {
            "openai_available": can_use_openai,
            "local_models": [
                {
                    "name": "Pattern Matching",
                    "description": "Rule-based causal relationship extraction",
                    "type": "local",
                    "capabilities": ["Basic causal extraction", "Pattern recognition"]
                },
                {
                    "name": "Statistical Analysis",
                    "description": "Statistical correlation analysis",
                    "type": "local",
                    "capabilities": ["Correlation analysis", "Statistical metrics"]
                }
            ]
        }
        
        if can_use_openai:
            models["openai_models"] = [
                {
                    "name": "GPT-4",
                    "description": "Advanced AI model for causal relationship extraction",
                    "type": "openai",
                    "capabilities": ["Advanced causal extraction", "Context understanding", "High accuracy"]
                }
            ]
        
        return models

# Global CDK service instance
cdk_service = CDKService()
