"""
IBVAP — Authentication & Authorization

Auth model: Supabase issues the JWT; the *application* role lives in the
`user_profiles` table. The Supabase `role` claim is always "authenticated" for
human users and must NOT be used for authorization. The app role is resolved
with a service-role client and cached briefly.
"""

import os
import time

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from loguru import logger
from supabase import create_client, Client

SUPABASE_URL = os.getenv("SUPABASE_URL", "http://127.0.0.1:54321")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")                  # anon key (fallback token check)
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")  # service_role — reads user_profiles
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")

# HS256 secret is project-wide, so also bind the issuer
_ISSUER = f"{SUPABASE_URL.rstrip('/')}/auth/v1"

VALID_ROLES = ("admin", "supervisor", "operator", "auditor")
DEFAULT_ROLE = "operator"

security = HTTPBearer()

_PROFILE_TTL = 60.0
_profile_cache: dict = {}          # user_id -> (expiry_ts, {"role", "allowed_areas"})
_service_client = None
_warned_no_service_key = False


def get_supabase() -> Client:
    """Anon Supabase client (kept for backward-compat)."""
    if not SUPABASE_KEY:
        logger.warning("SUPABASE_KEY is not set — Supabase client will not work.")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def _get_service_client():
    global _service_client, _warned_no_service_key
    if not SUPABASE_SERVICE_KEY:
        if not _warned_no_service_key:
            logger.warning(
                "SUPABASE_SERVICE_KEY not set — application roles cannot be resolved; "
                f"every authenticated user is treated as '{DEFAULT_ROLE}'."
            )
            _warned_no_service_key = True
        return None
    if _service_client is None:
        _service_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _service_client


def resolve_profile(user_id: str) -> dict:
    """Return {'role': str, 'allowed_areas': list[str]} for a user id, cached 60s."""
    now = time.time()
    hit = _profile_cache.get(user_id)
    if hit and hit[0] > now:
        return hit[1]

    profile = {"role": DEFAULT_ROLE, "allowed_areas": []}
    client = _get_service_client()
    if client is not None and user_id and user_id != "unknown":
        try:
            resp = (
                client.table("user_profiles")
                .select("role, allowed_areas")
                .eq("id", user_id)
                .limit(1)
                .execute()
            )
            row = (resp.data or [None])[0]
            if row:
                role = (row.get("role") or DEFAULT_ROLE).lower()
                profile["role"] = role if role in VALID_ROLES else DEFAULT_ROLE
                profile["allowed_areas"] = row.get("allowed_areas") or []
        except Exception as e:
            logger.error(f"resolve_profile({user_id}) failed: {e}")

    _profile_cache[user_id] = (now + _PROFILE_TTL, profile)
    return profile


def _verify_token(token: str) -> dict:
    """Verify a Supabase JWT and return its payload."""
    if SUPABASE_JWT_SECRET:
        try:
            return jwt.decode(
                token,
                SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated",
                issuer=_ISSUER,
                options={"require": ["exp", "sub", "aud"]},
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidTokenError as e:
            logger.warning(f"JWT rejected: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # Fallback: verify via the Supabase API (blocking; only when no local secret)
    try:
        client = get_supabase()
        user_response = client.auth.get_user(token)
        if user_response and user_response.user:
            return {
                "sub": user_response.user.id,
                "email": user_response.user.email,
                "role": "authenticated",
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token verification failed: {e}")

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_auth(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Validate the JWT and attach the resolved application role + area scope."""
    token = credentials.credentials
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = _verify_token(token)
    user_id = payload.get("sub", "unknown")
    profile = resolve_profile(user_id)

    return {
        "token": token,
        "user_id": user_id,
        "email": payload.get("email", ""),
        "app_role": profile["role"],
        "allowed_areas": profile["allowed_areas"],
        # legacy key retained so any un-migrated caller does not KeyError
        "role": profile["role"],
    }


def require_role(*roles: str):
    """Dependency factory: allow only the given application roles (admin always passes)."""
    allowed = set(roles) | {"admin"}

    async def _guard(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
        user = await require_auth(credentials)
        if user.get("app_role") not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of: {', '.join(sorted(allowed))}",
            )
        return user

    return _guard


require_admin = require_role("admin")


def scoped_cameras(user: dict):
    """Camera ids this user may see, or None for 'all'.

    admin, or an empty `allowed_areas`, => None (unrestricted).
    Populate `user_profiles.allowed_areas` to restrict an operator/auditor.
    """
    if user.get("app_role") == "admin":
        return None
    areas = user.get("allowed_areas") or []
    return list(areas) if areas else None
