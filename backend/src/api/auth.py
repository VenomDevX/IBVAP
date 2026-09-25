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
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from loguru import logger
from supabase import Client, create_client

from src.api.token_revocation import is_token_revoked

SUPABASE_URL = os.getenv("SUPABASE_URL", "http://127.0.0.1:54321")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")  # anon key (fallback token check)
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
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail=detail, headers={"WWW-Authenticate": "Bearer"}
    )


# Dev-only static-token bypass (off unless IBVAP_DEV_BYPASS is set)
_DEV_BYPASS = os.getenv("IBVAP_DEV_BYPASS", "").strip()
_IS_DEV = os.getenv("IBVAP_ENV", "development").lower() != "production"
if _DEV_BYPASS and _IS_DEV:
    logger.warning(
        "IBVAP_DEV_BYPASS is set — a static bearer token grants admin. Never use this outside local development."
    )

VALID_ROLES = ("admin", "commander", "operator", "viewer", "supervisor", "auditor")
DEFAULT_ROLE = "operator"

security = HTTPBearer()

_PROFILE_TTL = 60.0
_profile_cache: dict = {}  # user_id -> (expiry_ts, {"role", "allowed_areas"})
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
                "requests will be denied until role lookup is available."
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

    if user_id == "dev-admin" and _DEV_BYPASS and _IS_DEV:
        return {"role": "admin", "allowed_areas": []}

    try:
        client = _get_service_client()
        if client is None:
            raise RuntimeError("Profile service unavailable")
        resp = client.table("user_profiles").select("role, allowed_areas").eq("id", user_id).limit(1).execute()
        row = (resp.data or [None])[0]
    except Exception as e:
        logger.error(f"Profile lookup failed: {type(e).__name__}")
        raise HTTPException(status_code=503, detail="Authorization service unavailable") from e
    if not row or row.get("role") not in VALID_ROLES:
        raise HTTPException(status_code=403, detail="Application access is not configured")
    areas = row.get("allowed_areas")
    if not isinstance(areas, list) or any(not isinstance(a, str) or not a.strip() for a in areas):
        raise HTTPException(status_code=403, detail="Invalid camera access configuration")
    profile = {"role": row["role"], "allowed_areas": areas}

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
            payload = jwt.decode(token, SUPABASE_JWT_SECRET, algorithms=["HS256"], **kwargs)
        else:
            # asymmetric — verify against the project's published JWKS
            key = _jwks().get_signing_key_from_jwt(token).key
            payload = jwt.decode(token, key, algorithms=["ES256", "RS256", "RS384", "RS512", "EdDSA"], **kwargs)
    except jwt.ExpiredSignatureError:
        raise _unauth("Token has expired")
    except Exception as e:
        logger.warning(f"JWT rejected (alg={alg}): {e}")
        raise _unauth("Invalid authentication credentials")

    # Two-step verification is mandatory: a password-only (aal1) session gets nothing.
    if payload.get("aal") != "aal2":
        raise _unauth("mfa_required")
    return payload


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
    _deny_if_revoked(token)
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


def _deny_if_revoked(token: str) -> None:
    if is_token_revoked(token):
        raise _unauth("Token has been revoked")


_media_security = HTTPBearer(auto_error=False)


def issue_media_ticket(user: dict, lifetime_seconds: int = 120) -> str:
    """Issue a narrow, short-lived credential safe for media element URLs."""
    secret = os.getenv("EVIDENCE_HMAC_KEY") or os.getenv("SUPABASE_JWT_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="Media ticket signing is not configured")
    now = int(time.time())
    return jwt.encode(
        {
            "sub": user["user_id"], "email": user.get("email", ""),
            "app_role": user["app_role"], "allowed_areas": user["allowed_areas"],
            "iat": now, "exp": now + lifetime_seconds, "type": "media",
        },
        secret,
        algorithm="HS256",
    )


def _verify_media_ticket(ticket: str) -> dict:
    secret = os.getenv("EVIDENCE_HMAC_KEY") or os.getenv("SUPABASE_JWT_SECRET")
    if not secret:
        raise _unauth("Media ticket signing is not configured")
    try:
        payload = jwt.decode(ticket, secret, algorithms=["HS256"], options={"require": ["sub", "exp", "type"]})
    except jwt.PyJWTError as exc:
        raise _unauth("Invalid or expired media ticket") from exc
    if payload.get("type") != "media" or payload.get("app_role") not in VALID_ROLES:
        raise _unauth("Invalid media ticket")
    areas = payload.get("allowed_areas")
    if not isinstance(areas, list):
        raise _unauth("Invalid media scope")
    return {
        "token": ticket, "user_id": payload["sub"], "exp": payload["exp"],
        "email": payload.get("email", ""), "app_role": payload["app_role"],
        "allowed_areas": areas, "role": payload["app_role"],
    }


async def require_auth_media(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_media_security),
) -> dict:
    """Auth for <img>/<video> endpoints: bearer header OR ?token=<jwt>.

    Browsers can't set Authorization on <img src>, so the MJPEG stream / snapshot
    / heatmap endpoints accept the access token as a query param. (It lands in
    access logs — acceptable for these read-only media routes; nginx.conf turns
    logging off for them. Do not copy this pattern to data endpoints.)
    """
    ticket = request.query_params.get("ticket")
    if ticket:
        return _verify_media_ticket(ticket)
    token = credentials.credentials if credentials else request.query_params.get("token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = _verify_token(token)
    _deny_if_revoked(token)
    uid = payload.get("sub", "unknown")
    profile = resolve_profile(uid)
    return {
        "token": token,
        "user_id": uid,
        "exp": payload.get("exp"),
        "email": payload.get("email", ""),
        "app_role": profile["role"],
        "allowed_areas": profile["allowed_areas"],
        "role": profile["role"],
    }


def scoped_cameras(user: dict):
    """Camera ids this user may see, or None for 'all'.

    Only "admin" gets unrestricted (None). Every other role gets exactly the
    list in user_profiles.allowed_areas - including an EMPTY list, which means
    zero cameras, not all of them.

    Fail-closed by design: `allowed_areas` defaults to [] for a newly created
    profile (models.py) until an admin explicitly assigns cameras. Treating
    that default as "unrestricted" - the previous behaviour here - meant a
    brand-new operator or auditor account could see every camera in the
    system before anyone granted it access to any. An invalid or missing
    profile also gets [], for the same reason.
    """
    if user.get("app_role") == "admin":
        return None
    areas = user.get("allowed_areas")
    if user.get("app_role") not in VALID_ROLES or not isinstance(areas, list):
        return []
    return list(areas)


def can_access_camera(user: dict, camera_id: str) -> bool:
    allowed = scoped_cameras(user)
    return allowed is None or camera_id in allowed


def require_camera_access(user: dict, camera_id: str) -> None:
    if not can_access_camera(user, camera_id):
        raise HTTPException(status_code=403, detail="Camera access denied")


def refresh_media_identity(user: dict) -> dict:
    """Recheck long-lived connections, including logout and profile changes."""
    if user.get("exp") and time.time() >= user["exp"]:
        raise _unauth("Token has expired")
    _deny_if_revoked(user["token"])
    profile = resolve_profile(user["user_id"])
    return {**user, "app_role": profile["role"], "allowed_areas": profile["allowed_areas"]}
