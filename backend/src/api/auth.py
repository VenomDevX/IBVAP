from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import create_client, Client
import os

# The Supabase URL and Key should ideally come from environment variables.
# For local development with `npx supabase start`, we can use the default local values.
SUPABASE_URL = os.getenv("SUPABASE_URL", "http://127.0.0.1:54321")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "***REDACTED_SUPABASE_KEY***") # We will skip strict signature validation in dev if key is not set properly, or just rely on the token.

security = HTTPBearer()

def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

async def require_auth(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Validates the Supabase JWT token.
    For local dev, we just check if a token is provided.
    In production, you'd use the Supabase JWT secret to decode and verify.
    """
    token = credentials.credentials
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Normally we would verify the token here against Supabase.
    # For now, we accept any validly formatted Bearer token from the frontend.
    return {"token": token, "user_id": "supabase_user"}

async def require_admin(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Admin only route"""
    user = await require_auth(credentials)
    # Check roles if needed
    return user
