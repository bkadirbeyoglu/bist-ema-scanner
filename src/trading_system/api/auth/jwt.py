"""
JWT Authentication Utilities.

Handles token creation, validation, and password hashing.
"""

from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
import os
import logging

logger = logging.getLogger(__name__)

# JWT configuration
# SECURITY: Change these in production!
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-production")  # âš ï¸ Change this!
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# Password hashing context
# Uses pbkdf2_sha256 algorithm for secure password hashing
# WHY pbkdf2_sha256 instead of bcrypt?
# - Avoids bcrypt library version compatibility issues
# - Still very secure (used by Django by default)
# - Pure Python, no C library dependencies
# PRODUCTION NOTE: argon2 is the most modern choice if you need maximum security
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash.
    
    Args:
        plain_password: Password to verify
        hashed_password: Stored password hash
    
    Returns:
        True if password matches, False otherwise
    
    SECURITY: Uses constant-time comparison to prevent timing attacks
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    Hash a password for storage.
    
    Args:
        password: Plain text password
    
    Returns:
        Bcrypt hash of password
    
    SECURITY: Never store plain text passwords!
    """
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.
    
    Args:
        data: Payload to encode in token (usually {"sub": username})
        expires_delta: Token expiration time (default: 30 minutes)
    
    Returns:
        JWT token string
    
    JWT STRUCTURE:
    - Header: Algorithm and token type
    - Payload: User data and claims (exp, iat, sub)
    - Signature: Prevents tampering
    
    Example token:
    eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.
    eyJzdWIiOiJ0cmFkZXIxIiwiZXhwIjoxNjQwOTk1MjAwfQ.
    SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # Add standard JWT claims
    to_encode.update({
        "exp": expire,  # Expiration time
        "iat": datetime.utcnow()  # Issued at time
    })
    
    # Create signed token
    # SECURITY: Signature prevents token modification
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[str]:
    """
    Decode and validate a JWT token.
    
    Args:
        token: JWT token string
    
    Returns:
        Username from token, or None if invalid
    
    SECURITY: Validates:
    - Signature is correct
    - Token hasn't expired
    - Token structure is valid
    """
    try:
        # Decode and validate token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        # Extract username from 'sub' claim
        username: str = payload.get("sub")
        if username is None:
            return None
        
        return username
    
    except JWTError as e:
        logger.warning(f"JWT validation error: {e}")
        return None


# Mock user database (for demonstration)
# PRODUCTION: Replace with real database queries
FAKE_USERS_DB = {
    "trader1": {
        "username": "trader1",
        "full_name": "Test Trader",
        "email": "trader1@example.com",
        "plain_password": "password123",  # Will be hashed on first access
        "hashed_password": None,  # Lazy initialized
        "disabled": False,
    },
    "admin": {
        "username": "admin",
        "full_name": "System Admin",
        "email": "admin@example.com",
        "plain_password": "admin123",
        "hashed_password": None,
        "disabled": False,
    }
}


def get_user(username: str) -> Optional[dict]:
    """Get user and ensure password is hashed (lazy initialization)."""
    user = FAKE_USERS_DB.get(username)
    if user and user["hashed_password"] is None:
        user["hashed_password"] = get_password_hash(user["plain_password"])
    return user


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """
    Authenticate a user by username and password.
    
    Args:
        username: Username to authenticate
        password: Plain text password
    
    Returns:
        User dict if authenticated, None otherwise
    
    PRODUCTION: Replace with real database query
    """
    user = get_user(username)  # Uses lazy hash initialization
    if not user:
        return None
    if not verify_password(password, user["hashed_password"]):
        return None
    return user