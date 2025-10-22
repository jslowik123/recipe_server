from fastapi import Depends, status
from fastapi.responses import JSONResponse
from src.config import config
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError

security = HTTPBearer()

class TokenError(Exception):
    """Custom exception for token errors"""
    def __init__(self, error_code: str, technical_details: str):
        self.error_code = error_code
        self.technical_details = technical_details
        super().__init__(technical_details)

def verify_token_sync(credentials: HTTPAuthorizationCredentials) -> str:
    """Synchronous JWT token verification"""
    try:
        jwt_secret = config.supabase_jwt_secret
    except Exception:
        raise TokenError(
            error_code="INTERNAL_SERVER_ERROR",
            technical_details="JWT Secret not configured"
        )

    token = credentials.credentials
    try:
        # JWT verifizieren
        payload = jwt.decode(
            token,
            jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",  # Muss mit Supabase übereinstimmen
        )
        user_id = payload.get("sub")  # Enthält die Supabase User-ID
        if user_id is None:
            raise TokenError(
                error_code="INVALID_TOKEN",
                technical_details="Token does not contain user ID"
            )
        return user_id
    except jwt.ExpiredSignatureError:
        raise TokenError(
            error_code="EXPIRED_TOKEN",
            technical_details="Token has expired"
        )
    except JWTError:
        raise TokenError(
            error_code="INVALID_TOKEN",
            technical_details="Invalid token signature"
        )

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Async wrapper for JWT verification (for dependency injection)"""
    return verify_token_sync(credentials)
