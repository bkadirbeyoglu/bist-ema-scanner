"""
Authentication API Router.

Provides token endpoint for JWT authentication.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from datetime import timedelta
import logging

from trading_system.api.auth.jwt import (
    authenticate_user,
    create_access_token,
    decode_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from trading_system.api.schemas.responses import TokenResponse, ErrorResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# OAuth2 scheme for token authentication
# FASTAPI SECURITY: Automatically handles "Authorization: Bearer <token>" headers
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


@router.post(
    "/token",
    response_model=TokenResponse,
    summary="Get access token",
    description="Authenticate and receive JWT access token",
    responses={
        200: {"description": "Token generated successfully"},
        401: {"model": ErrorResponse, "description": "Invalid credentials"}
    }
)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    OAuth2 compatible token endpoint.
    
    **Request Body (form data):**
    - `username`: User's username
    - `password`: User's password
    
    **Returns:** JWT access token
    
    **Example (curl):**
```bash
    curl -X POST http://localhost:8000/api/v1/auth/token \
      -H "Content-Type: application/x-www-form-urlencoded" \
      -d "username=trader1&password=password123"
```
    
    **Example (httpie):**
```bash
    http --form POST localhost:8000/api/v1/auth/token \
      username=trader1 password=password123
```
    
    **Test Credentials:**
    - Username: `trader1`, Password: `password123`
    - Username: `admin`, Password: `admin123`
    """
    # Authenticate user
    user = authenticate_user(form_data.username, form_data.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create access token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"]},
        expires_delta=access_token_expires
    )
    
    logger.info(f"User '{user['username']}' authenticated successfully")
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60  # Convert to seconds
    )


async def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    """
    Dependency to get current authenticated user.
    
    FASTAPI DEPENDENCY: Use in endpoints that require authentication:
```python
    @router.get("/protected")
    async def protected_endpoint(username: str = Depends(get_current_user)):
        return {"message": f"Hello {username}!"}
```
    
    SECURITY: Automatically validates JWT token from Authorization header
    """
    username = decode_access_token(token)
    
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return username


# Example protected endpoint
@router.get(
    "/me",
    summary="Get current user",
    description="Get information about the currently authenticated user",
    responses={
        200: {"description": "User information"},
        401: {"model": ErrorResponse, "description": "Not authenticated"}
    }
)
async def read_users_me(username: str = Depends(get_current_user)):
    """
    Get current user information.
    
    **Requires:** Valid JWT token in Authorization header
    
    **Example:**
```bash
    curl http://localhost:8000/api/v1/auth/me \
      -H "Authorization: Bearer eyJ..."
```
    
    **Returns:** Current user's information
    """
    return {
        "username": username,
        "message": "You are authenticated!"
    }