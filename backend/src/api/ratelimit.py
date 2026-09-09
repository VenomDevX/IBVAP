"""
Shared rate limiter.

Lives in its own module so route files can hang `@limiter.limit(...)` off it
without importing `src.api.app` (which imports the routes — circular).

Default (global) limits are a sustained cap plus a short burst cap. Expensive or
abuse-prone routes add a tighter per-route `@limiter.limit(...)`.
"""

from slowapi import Limiter

from src.api.net import client_ip

limiter = Limiter(key_func=client_ip, default_limits=["600/minute", "20/second"])
