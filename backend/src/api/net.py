"""
Client-address resolution shared by the rate limiter and request logging.

Behind nginx every request's peer address is the proxy's, so a single global
rate-limit bucket lumps all users together. When the deployment sets
``TRUSTED_PROXY=1`` we take the first hop of ``X-Forwarded-For`` instead — but
never otherwise, because that header is client-controlled.
"""

import os

from starlette.requests import Request

_TRUSTED = os.getenv("TRUSTED_PROXY", "").lower() in ("1", "true", "yes")


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    if _TRUSTED:
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            first = xff.split(",")[0]
            return "".join(first.split())[:64] or peer
    return peer
