"""
Error handling middleware for CausalGraph Platform
Provides centralized error handling and logging
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import time
from typing import Union

from utils.exceptions import CausalGraphException
from utils.logger import logger
from utils.response_models import ErrorResponse

async def error_handler_middleware(request: Request, call_next):
    """
    Middleware to handle errors and provide consistent error responses
    """
    start_time = time.time()
    
    try:
        response = await call_next(request)
        
        # Log successful requests
        process_time = time.time() - start_time
        logger.info(f"Request {request.method} {request.url.path} completed in {process_time:.3f}s")
        
        return response
        
    except Exception as exc:
        process_time = time.time() - start_time
        
        # Handle different types of exceptions
        if isinstance(exc, CausalGraphException):
            error_response = ErrorResponse(
                message=exc.message,
                error_code=exc.error_code,
                details=exc.details
            )
            logger.error(f"Application error: {exc.message}", extra=exc.details)
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=error_response.dict()
            )
            
        elif isinstance(exc, RequestValidationError):
            error_response = ErrorResponse(
                message="Request validation failed",
                error_code="VALIDATION_ERROR",
                details={"validation_errors": exc.errors()}
            )
            logger.warning(f"Validation error: {exc.errors()}")
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content=error_response.dict()
            )
            
        elif isinstance(exc, StarletteHTTPException):
            error_response = ErrorResponse(
                message=exc.detail,
                error_code="HTTP_ERROR",
                details={"status_code": exc.status_code}
            )
            logger.warning(f"HTTP error {exc.status_code}: {exc.detail}")
            return JSONResponse(
                status_code=exc.status_code,
                content=error_response.dict()
            )
            
        else:
            # Handle unexpected errors
            error_response = ErrorResponse(
                message="Internal server error",
                error_code="INTERNAL_ERROR",
                details={"error_type": type(exc).__name__}
            )
            logger.error(f"Unexpected error: {str(exc)}", exc_info=True)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=error_response.dict()
            )

def setup_error_handlers(app):
    """
    Setup error handlers for the FastAPI application
    """
    app.middleware("http")(error_handler_middleware)
    
    @app.exception_handler(CausalGraphException)
    async def causal_graph_exception_handler(request: Request, exc: CausalGraphException):
        """Handle CausalGraph exceptions"""
        error_response = ErrorResponse(
            message=exc.message,
            error_code=exc.error_code,
            details=exc.details
        )
        logger.error(f"CausalGraph exception: {exc.message}", extra=exc.details)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=error_response.dict()
        )
    
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Handle validation exceptions"""
        error_response = ErrorResponse(
            message="Request validation failed",
            error_code="VALIDATION_ERROR",
            details={"validation_errors": exc.errors()}
        )
        logger.warning(f"Validation exception: {exc.errors()}")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_response.dict()
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle general exceptions"""
        error_response = ErrorResponse(
            message="Internal server error",
            error_code="INTERNAL_ERROR",
            details={"error_type": type(exc).__name__}
        )
        logger.error(f"General exception: {str(exc)}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response.dict()
        )
