"""
Authentication service for CausalGraph.AI platform
Handles user authentication, JWT tokens, and password security
"""

import jwt
import bcrypt
import uuid
from datetime import datetime, timedelta
from typing import Optional
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import aiosqlite
from database import get_db
from models import User, UserCreate, UserLogin, Token, UserResponse

# JWT configuration
SECRET_KEY = "your-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

security = HTTPBearer()

class AuthService:
    def __init__(self):
        self.secret_key = SECRET_KEY
        self.algorithm = ALGORITHM
        self.access_token_expire_minutes = ACCESS_TOKEN_EXPIRE_MINUTES
    
    def hash_password(self, password: str) -> str:
        """Hash password using bcrypt"""
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    
    def verify_password(self, password: str, hashed_password: str) -> bool:
        """Verify password against hash"""
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
    
    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None):
        """Create JWT access token"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)
        
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt
    
    def verify_token(self, token: str) -> dict:
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired"
            )
        except jwt.JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
    
    async def create_user(self, user_data: UserCreate, db: aiosqlite.Connection) -> UserResponse:
        """Create new user account"""
        # Check if user already exists
        cursor = await db.execute("SELECT id FROM users WHERE email = ?", (user_data.email,))
        if await cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Create user
        user_id = str(uuid.uuid4())
        hashed_password = self.hash_password(user_data.password)
        
        await db.execute("""
            INSERT INTO users (id, email, username, password_hash, role, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, user_data.email, user_data.username, hashed_password, user_data.role.value, datetime.utcnow()))
        
        await db.commit()
        
        # Return user without password
        return UserResponse(
            id=user_id,
            email=user_data.email,
            username=user_data.username,
            role=user_data.role,
            created_at=datetime.utcnow()
        )
    
    async def authenticate_user(self, user_data: UserLogin, db: aiosqlite.Connection) -> UserResponse:
        """Authenticate user and return user data"""
        cursor = await db.execute("""
            SELECT id, email, username, password_hash, role, created_at, is_active
            FROM users WHERE email = ?
        """, (user_data.email,))
        
        user_row = await cursor.fetchone()
        if not user_row:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        if not user_row[6]:  # is_active column
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is deactivated"
            )
        
        if not self.verify_password(user_data.password, user_row[3]):  # password_hash column
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        return UserResponse(
            id=user_row[0],  # id column
            email=user_row[1],  # email column
            username=user_row[2],  # username column
            role=user_row[4],  # role column
            created_at=user_row[5]  # created_at column
        )
    
    async def login_user(self, user_data: UserLogin, db: aiosqlite.Connection) -> Token:
        """Login user and return access token"""
        user = await self.authenticate_user(user_data, db)
        
        access_token_expires = timedelta(minutes=self.access_token_expire_minutes)
        access_token = self.create_access_token(
            data={"sub": user.id, "email": user.email, "role": user.role.value},
            expires_delta=access_token_expires
        )
        
        return Token(access_token=access_token, user_id=user.id)
    
    async def get_current_user(self, credentials: HTTPAuthorizationCredentials = Depends(security), db: aiosqlite.Connection = Depends(get_db)) -> UserResponse:
        """Get current authenticated user from token"""
        token = credentials.credentials
        payload = self.verify_token(token)
        
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        
        cursor = await db.execute("""
            SELECT id, email, username, role, created_at
            FROM users WHERE id = ? AND is_active = 1
        """, (user_id,))
        
        user_row = await cursor.fetchone()
        if not user_row:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )
        
        return UserResponse(
            id=user_row[0],  # id column
            email=user_row[1],  # email column
            username=user_row[2],  # username column
            role=user_row[3],  # role column
            created_at=user_row[4]  # created_at column
        )

# Global auth service instance
auth_service = AuthService()

# Dependency for getting current user
async def get_current_user_dependency(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: aiosqlite.Connection = Depends(get_db)
) -> UserResponse:
    return await auth_service.get_current_user(credentials, db)
