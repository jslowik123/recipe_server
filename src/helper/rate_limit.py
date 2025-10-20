from typing import Union
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
import logging

logger = logging.getLogger(__name__)

def rate_limit_handler(request: Request, exc: Union[RateLimitExceeded, Exception]) -> Response:
    return JSONResponse(
        status_code=429,
        content={
            "error": "Rate limit exceeded",
            "detail": "Too many requests. Please try again later."
        }
    )

def anonymize_ip(ip_address: str) -> str:
    """Anonymize IP address for GDPR compliance"""
    if not ip_address:
        return "unknown"

    # IPv4: 192.168.1.123 -> 192.168.x.x
    if "." in ip_address and ":" not in ip_address:
        parts = ip_address.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.x.x"

    # IPv6: 2001:0db8:85a3:0000:0000:8a2e:0370:7334 -> 2001:0db8:x:x:x:x:x:x
    elif ":" in ip_address:
        parts = ip_address.split(":")
        if len(parts) >= 3:
            return f"{parts[0]}:{parts[1]}:x:x:x:x:x:x"

    return "unknown"

# user identifier for rate limiting the user_id
def get_user_identifier(request: Request):
    user_id = getattr(request.state, 'user_id', None)
    if user_id:
        logger.info(f"Rate limiting by user_id: {user_id}")
        return user_id
    else:
        ip_address = get_remote_address(request)
        anonymized_ip = anonymize_ip(ip_address)
        logger.info(f"Rate limiting by IP address: {anonymized_ip}")
        return ip_address

