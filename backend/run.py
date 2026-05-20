#!/usr/bin/env python3
"""
CausalGraph Platform - Server Entry Point
Main script for starting the FastAPI server
"""

import uvicorn
import os
from dotenv import load_dotenv
from config import Config

def main():
    """Main function to start the FastAPI server"""
    # Load environment variables
    load_dotenv()
    
    # Get configuration from environment
    host = Config.HOST
    port = Config.PORT
    debug = Config.DEBUG
    
    print("Starting CausalGraph Platform Server...")
    print(f"Server will run on http://{host}:{port}")
    print(f"Debug mode: {debug}")
    print("=" * 50)
    
    # Start the server
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=debug,
        log_level="info"
    )

if __name__ == "__main__":
    main()
