"""slowapi rate limiting (SPEC 1.7): 30 requests/minute per IP on POSTs."""

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

__all__ = ["limiter", "RateLimitExceeded", "get_remote_address"]
