from fastapi import HTTPException, Depends, status, WebSocket, WebSocketDisconnect, Query, Request
from src.config import config
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError

security = HTTPBearer()

def verify_token_sync(credentials: HTTPAuthorizationCredentials,) -> str:
    """Synchronous JWT token verification"""
    try:
        jwt_secret = config.supabase_jwt_secret
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT Secret nicht konfiguriert",
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
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Ungültiger Token",
            )
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token ist abgelaufen",
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiger Token",
        )

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Async wrapper for JWT verification (for dependency injection)"""
    return verify_token_sync(credentials)
