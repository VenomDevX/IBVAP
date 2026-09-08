"""
IBVAP — Security Middleware
===========================
- Request logging with IP, user agent, endpoint, response time
- Security headers (X-Content-Type-Options, X-Frame-Options, etc.)
- Request ID tracking for audit trails
"""

import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from loguru import logger


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds security headers to all responses to prevent common attacks:
    - XSS (Cross-Site Scripting)
    - Clickjacking
    - MIME-type sniffing
    - Information leakage
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Prevent MIME-type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent clickjacking — only allow same-origin framing
        response.headers["X-Frame-Options"] = "SAMEORIGIN"

        # Enable browser XSS protection
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Control referrer information leakage
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Prevent browsers from caching sensitive responses
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"

        # Remove server identification header
        response.headers.pop("server", None)

        # Content Security Policy for any HTML responses
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' data: blob:; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "connect-src 'self' ws: wss:;"
        )

        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Logs every API request with:
    - Unique request ID (for audit trail)
    - Client IP address
    - User agent
    - Endpoint and method
    - Response status code
    - Response time (ms)
    """

    # Paths to skip logging (noisy health checks, static files)
    SKIP_PATHS = {"/api/health", "/favicon.ico"}

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip noisy endpoints
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        # Generate unique request ID
        request_id = str(uuid.uuid4())[:8]

        # Extract client info
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")[:100]
        method = request.method
        path = request.url.path

        # Forward headers for proxy deployments
        forwarded_for = request.headers.get("x-forwarded-for", "")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()

        start_time = time.time()

        try:
            response = await call_next(request)
            elapsed_ms = (time.time() - start_time) * 1000

            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id

            # Log the request
            log_msg = (
                f"[{request_id}] {method} {path} → {response.status_code} "
                f"({elapsed_ms:.0f}ms) | IP: {client_ip} | UA: {user_agent[:50]}"
            )

            if response.status_code >= 500:
                logger.error(log_msg)
            elif response.status_code >= 400:
                logger.warning(log_msg)
            else:
                logger.info(log_msg)

            return response

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error(
                f"[{request_id}] {method} {path} → EXCEPTION ({elapsed_ms:.0f}ms) "
                f"| IP: {client_ip} | Error: {e}"
            )
            raise
