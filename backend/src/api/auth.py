"""
IBVAP — Authentication & Authorization
JWT verification via Supabase, with role-based access control.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import create_client, Client
import os
import jwt
from loguru import logger

# Supabase configuration — MUST be set via environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL", "http://127.0.0.1:54321")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")

security = HTTPBearer()


def get_supabase() -> Client:
    if not SUPABASE_KEY:
        logger.warning("SUPABASE_KEY is not set — Supabase client will not work.")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def _verify_token(token: str) -> dict:
    """
    Verify a Supabase JWT token and return the decoded payload.
    Falls back to Supabase API verification if JWT_SECRET is not set.
    """
    # Method 1: Local JWT verification (preferred — no network call)
    if SUPABASE_JWT_SECRET:
        try:
            payload = jwt.decode(
                token,
                SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated",
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidTokenError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {e}",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # Method 2: Verify via Supabase API (fallback)
    try:
        supabase = get_supabase()
        user_response = supabase.auth.get_user(token)
        if user_response and user_response.user:
            return {
                "sub": user_response.user.id,
                "email": user_response.user.email,
                "role": user_response.user.role or "authenticated",
            }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def require_auth(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Validates the Supabase JWT token.
    Returns user info dict with at least 'user_id' and 'role'.
    """
    token = credentials.credentials
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = _verify_token(token)

    return {
        "token": token,
        "user_id": payload.get("sub", "unknown"),
        "email": payload.get("email", ""),
        "role": payload.get("role", "authenticated"),
    }


async def require_admin(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Admin-only route guard."""
    user = await require_auth(credentials)
    if user.get("role") not in ("admin", "service_role"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user
