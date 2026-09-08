"""
IBVAP — Authentication & Authorization

Auth model: Supabase issues the JWT; the *application* role lives in the
`user_profiles` table. The Supabase `role` claim is always "authenticated" for
human users and must NOT be used for authorization. The app role is resolved
with a service-role client and cached briefly.

Dev bypass: set IBVAP_DEV_BYPASS=<token> (and keep IBVAP_ENV != production) to accept
that exact bearer token as an admin without Supabase. Off by default.
"""

import os
import time

import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from loguru import logger
from supabase import create_client, Client

SUPABASE_URL = os.getenv("SUPABASE_URL", "http://127.0.0.1:54321")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")                  # anon key (fallback token check)
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")  # service_role — reads user_profiles
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")
# Optional: enforce the token `iss`. Leave unset unless you know the exact issuer string
# (decode a real token from supabase.auth.getSession()). A mismatch rejects every token.
SUPABASE_JWT_ISSUER = os.getenv("SUPABASE_JWT_ISSUER", "").strip() or None

# Modern Supabase signs user access tokens with an asymmetric key (ES256/RS256)
# published via JWKS. The legacy shared HS256 secret only covers the static
# anon/service_role keys, so we must verify real tokens against the JWKS.
_JWKS_URL = f"{SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"
_jwks_client = None


def _jwks():
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(_JWKS_URL, cache_keys=True, lifespan=3600)
    return _jwks_client


def _unauth(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail,
                         headers={"WWW-Authenticate": "Bearer"})

# Dev-only static-token bypass (off unless IBVAP_DEV_BYPASS is set)
_DEV_BYPASS = os.getenv("IBVAP_DEV_BYPASS", "").strip()
_IS_DEV = os.getenv("IBVAP_ENV", "development").lower() != "production"
if _DEV_BYPASS and _IS_DEV:
    logger.warning("IBVAP_DEV_BYPASS is set — a static bearer token grants admin. "
                   "Never use this outside local development.")

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

    if user_id == "dev-admin":
        return {"role": "admin", "allowed_areas": []}

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
    if _DEV_BYPASS and _IS_DEV and token == _DEV_BYPASS:
        return {"sub": "dev-admin", "email": "admin@ibvap.local", "role": "authenticated"}

    try:
        alg = jwt.get_unverified_header(token).get("alg", "")
    except jwt.InvalidTokenError:
        raise _unauth("Invalid authentication credentials")

    kwargs = dict(audience="authenticated", options={"require": ["exp", "sub", "aud"]})
    if SUPABASE_JWT_ISSUER:
        kwargs["issuer"] = SUPABASE_JWT_ISSUER

    try:
        if alg == "HS256":
            if not SUPABASE_JWT_SECRET:
                raise jwt.InvalidTokenError("HS256 token but SUPABASE_JWT_SECRET is unset")
            return jwt.decode(token, SUPABASE_JWT_SECRET, algorithms=["HS256"], **kwargs)
        # asymmetric — verify against the project's published JWKS
        key = _jwks().get_signing_key_from_jwt(token).key
        return jwt.decode(token, key, algorithms=["ES256", "RS256", "RS384", "RS512", "EdDSA"], **kwargs)
    except jwt.ExpiredSignatureError:
        raise _unauth("Token has expired")
    except Exception as e:
        logger.warning(f"JWT rejected (alg={alg}): {e}")
        raise _unauth("Invalid authentication credentials")


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
