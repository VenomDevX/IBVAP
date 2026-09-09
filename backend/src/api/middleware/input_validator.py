"""
IBVAP — Input Validation Middleware
====================================
Cheap, first-pass request guards:
- Content-Length vs. the upload cap
- Path-traversal patterns in the request path (raw + URL-decoded)
- Obvious injection markers in the query string AND in JSON/form request bodies
  (raw + URL-decoded, so a percent-encoded payload can't slip past)

This is a coarse net, not the primary defence — route handlers still validate
their inputs with Pydantic, and uploaded files must go through
``validate_image_file``. Body scanning is capped and skips binary uploads.
"""

import os
import re
from urllib.parse import unquote_plus

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# Maximum upload size: 50 MB
MAX_UPLOAD_SIZE = 50 * 1024 * 1024

# Only scan bodies up to this size (JSON/form payloads are small; don't stall uploads).
MAX_BODY_SCAN = 256 * 1024

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/bmp", "image/webp", "image/gif"}
ALLOWED_VIDEO_TYPES = {
    "video/mp4",
    "video/avi",
    "video/x-msvideo",
    "video/quicktime",
    "video/x-matroska",
    "video/webm",
}

IMAGE_SIGNATURES = {
    b"\xff\xd8\xff": "jpeg",
    b"\x89PNG\r\n\x1a\n": "png",
    b"BM": "bmp",
    b"RIFF": "webp",
    b"GIF8": "gif",
}

# Traversal markers — the raw request path plus one decode pass.
PATH_TRAVERSAL_PATTERN = re.compile(r"\.\.[\\/]|\.\.%2f|%2e%2e|%252e|%c0%ae|%c1%9c", re.IGNORECASE)

# Injection markers. Deliberately specific so ordinary params like `?online=true`
# or `?section=events` do NOT trip it — the old `on\w+=` rule did.
INJECTION_PATTERN = re.compile(
    r"(?:"
    r"<\s*script\b|</\s*script\s*>|<\s*iframe\b|"
    r"javascript:|vbscript:|data:text/html|"
    r"\bon(?:error|load|click|mouseover|focus|submit)\s*=|"
    r"\beval\s*\(|\bexec\s*\(|\bsystem\s*\(|__import__|"
    r"/etc/passwd|cmd\.exe|/bin/(?:ba)?sh\b"
    r")",
    re.IGNORECASE,
)

_SCANNABLE_BODY_TYPES = ("application/json", "application/x-www-form-urlencoded", "text/plain", "multipart/form-data")


def _both(s: str) -> tuple[str, str]:
    """The string and its URL-decoded form (one pass covers single-encoding)."""
    try:
        return s, unquote_plus(s)
    except Exception:
        return s, s


class InputValidationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"

        for variant in _both(request.url.path):
            if PATH_TRAVERSAL_PATTERN.search(variant):
                logger.warning(f"BLOCKED path traversal: {request.url.path} | IP: {client_ip}")
                return JSONResponse(status_code=400, content={"detail": "Invalid path"})

        query = str(request.url.query or "")
        for variant in _both(query):
            if INJECTION_PATTERN.search(variant):
                logger.warning(f"BLOCKED injection in query: {query[:200]} | IP: {client_ip}")
                return JSONResponse(status_code=400, content={"detail": "Invalid request parameters"})

        content_length = request.headers.get("content-length")
        if content_length:
            try:
                too_big = int(content_length) > MAX_UPLOAD_SIZE
            except ValueError:
                too_big = True
            if too_big:
                logger.warning(f"BLOCKED oversized/invalid Content-Length: {content_length!r}")
                return JSONResponse(
                    status_code=413,
                    content={"detail": f"Upload too large. Maximum size: {MAX_UPLOAD_SIZE // (1024 * 1024)} MB"},
                )

        # --- request body ---
        ctype = request.headers.get("content-type", "").lower()
        if (
            request.method in ("POST", "PUT", "PATCH", "DELETE")
            and any(t in ctype for t in _SCANNABLE_BODY_TYPES)
            and "multipart/form-data" not in ctype  # file uploads: validate_image_file handles these
        ):
            body = await request.body()
            if body and len(body) <= MAX_BODY_SCAN:
                text = body.decode("utf-8", "ignore")
                for variant in _both(text):
                    if INJECTION_PATTERN.search(variant):
                        logger.warning(f"BLOCKED injection in body: {text[:200]} | IP: {client_ip}")
                        return JSONResponse(status_code=400, content={"detail": "Invalid request body"})
            # let downstream read the body again
            request._body = body

            async def _receive():
                return {"type": "http.request", "body": body, "more_body": False}

            request._receive = _receive

        return await call_next(request)


def validate_image_file(file_content: bytes, filename: str) -> tuple[bool, str]:
    """Validate an uploaded image (size, extension, magic bytes, embedded scripts).

    Call from any route that accepts an image upload::

        content = await file.read()
        ok, err = validate_image_file(content, file.filename)
        if not ok:
            raise HTTPException(400, detail=err)
    """
    if len(file_content) > MAX_UPLOAD_SIZE:
        return False, f"File too large ({len(file_content)} bytes). Max: {MAX_UPLOAD_SIZE // (1024 * 1024)} MB"

    ext = os.path.splitext(filename.lower())[1]
    allowed_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif"}
    if ext not in allowed_exts:
        return False, f"Invalid file type: {ext}. Allowed: {', '.join(sorted(allowed_exts))}"

    if not any(file_content[: len(sig)] == sig for sig in IMAGE_SIGNATURES):
        return False, "File content does not match a valid image format"

    for pattern in (b"<script", b"javascript:", b"<?php", b"eval("):
        if pattern in file_content[:4096]:
            return False, "Suspicious content detected in file"

    return True, ""


_CAMERA_ID_RE = re.compile(r"[^A-Za-z0-9_\-]")


def sanitize_camera_id(camera_id: str) -> str:
    """Strip anything but ``[A-Za-z0-9_-]`` from a camera id before it reaches a
    filesystem path or a shell. Defence-in-depth — the pipeline dict lookup would
    already reject an unknown id."""
    sanitized = _CAMERA_ID_RE.sub("", camera_id or "")
    if sanitized != camera_id:
        logger.warning(f"Sanitized camera_id: {camera_id!r} -> {sanitized!r}")
    return sanitized
