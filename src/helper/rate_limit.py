from typing import Union
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

def rate_limit_handler(request: Request, exc: Union[RateLimitExceeded, Exception]) -> Response:
    return JSONResponse(
        status_code=429,
        content={
            "error": "Rate limit exceeded",
            "detail": "Too many requests. Please try again later."
        }
    )
# user identifier for rate limiting the user_id
def get_user_identifier(request: Request):
    return request.state.user_id or get_remote_address(request)

