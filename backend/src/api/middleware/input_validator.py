"""
IBVAP — Input Validation Middleware
====================================
- Validates uploaded files (size, type, content)
- Sanitizes path parameters to prevent path traversal
- Blocks suspicious payloads
"""

import re
import os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from loguru import logger

# Maximum upload size: 50 MB
MAX_UPLOAD_SIZE = 50 * 1024 * 1024

# Allowed image MIME types
ALLOWED_IMAGE_TYPES = {
    "image/jpeg", "image/png", "image/bmp", "image/webp", "image/gif"
}

# Allowed video MIME types
ALLOWED_VIDEO_TYPES = {
    "video/mp4", "video/avi", "video/x-msvideo", "video/quicktime",
    "video/x-matroska", "video/webm"
}

# Image file magic bytes (file signatures)
IMAGE_SIGNATURES = {
    b"\xff\xd8\xff": "jpeg",
    b"\x89PNG\r\n\x1a\n": "png",
    b"BM": "bmp",
    b"RIFF": "webp",  # WebP starts with RIFF
    b"GIF8": "gif",
}

# Dangerous path patterns
PATH_TRAVERSAL_PATTERN = re.compile(r"\.\.|%2e%2e|%252e|%c0%ae|%c1%9c", re.IGNORECASE)

# Dangerous characters in query/path params
INJECTION_PATTERN = re.compile(
    r"(<script|javascript:|on\w+=|eval\(|exec\(|system\(|__import__|cmd\.exe|/etc/passwd)",
    re.IGNORECASE
)


class InputValidationMiddleware(BaseHTTPMiddleware):
    """
    Validates all incoming requests for security:
    1. Checks Content-Length against max upload size
    2. Validates path parameters for traversal attacks
    3. Checks for injection attempts in query strings
    """

    async def dispatch(self, request: Request, call_next):
        # 1. Check for path traversal
        raw_path = request.url.path
        if PATH_TRAVERSAL_PATTERN.search(raw_path):
            client_ip = request.client.host if request.client else "unknown"
            logger.warning(
                f"BLOCKED path traversal attempt: {raw_path} | IP: {client_ip}"
            )
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid path"}
            )

        # 2. Check query params for injection
        query_string = str(request.url.query or "")
        if INJECTION_PATTERN.search(query_string):
            client_ip = request.client.host if request.client else "unknown"
            logger.warning(
                f"BLOCKED injection attempt in query: {query_string[:200]} | IP: {client_ip}"
            )
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid request parameters"}
            )

        # 3. Check Content-Length for uploads
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_UPLOAD_SIZE:
            logger.warning(
                f"BLOCKED oversized upload: {int(content_length)} bytes "
                f"(max: {MAX_UPLOAD_SIZE}) | IP: {request.client.host}"
            )
            return JSONResponse(
                status_code=413,
                content={"detail": f"Upload too large. Maximum size: {MAX_UPLOAD_SIZE // (1024*1024)} MB"}
            )

        return await call_next(request)


def validate_image_file(file_content: bytes, filename: str) -> tuple[bool, str]:
    """
    Validate an uploaded image file.
    Returns (is_valid, error_message).
    
    Use this in route handlers that accept image uploads:
        from src.api.middleware.input_validator import validate_image_file
        
        content = await file.read()
        is_valid, error = validate_image_file(content, file.filename)
        if not is_valid:
            raise HTTPException(400, detail=error)
    """
    # Check size
    if len(file_content) > MAX_UPLOAD_SIZE:
        return False, f"File too large ({len(file_content)} bytes). Max: {MAX_UPLOAD_SIZE // (1024*1024)} MB"

    # Check file extension
    ext = os.path.splitext(filename.lower())[1]
    allowed_exts = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.gif'}
    if ext not in allowed_exts:
        return False, f"Invalid file type: {ext}. Allowed: {', '.join(allowed_exts)}"

    # Check magic bytes (file signature)
    is_valid_sig = False
    for sig, fmt in IMAGE_SIGNATURES.items():
        if file_content[:len(sig)] == sig:
            is_valid_sig = True
            break

    if not is_valid_sig:
        return False, "File content does not match a valid image format"

    # Check for embedded scripts in image metadata
    # (Some attacks embed JavaScript in EXIF data)
    suspicious_patterns = [b"<script", b"javascript:", b"<?php", b"eval("]
    for pattern in suspicious_patterns:
        if pattern in file_content[:4096]:  # Check first 4KB
            return False, "Suspicious content detected in file"

    return True, ""


def sanitize_camera_id(camera_id: str) -> str:
    """
    Sanitize a camera ID to prevent path traversal and injection.
    Only allows alphanumeric, hyphens, underscores.
    """
    sanitized = re.sub(r"[^a-zA-Z0-9_\-]", "", camera_id)
    if sanitized != camera_id:
        logger.warning(f"Sanitized camera_id: '{camera_id}' → '{sanitized}'")
    return sanitized
