import fastapi
import uvicorn
import logging
from fastapi import Depends, status, WebSocket, WebSocketDisconnect, Query, Request
from src.helper.verify_token import verify_token, verify_token_sync, security, TokenError
logger = logging.getLogger(__name__)

app = fastapi.FastAPI(
    title="jwt test",
    version="1.0.0",
)

@app.head("/test")
@app.get("/test")
def read_root(user_id: str = Depends(verify_token)):
    return {"user_id": user_id}


if __name__ == "__main__":
    uvicorn.run("jwt_test:app", host="0.0.0.0", port=8000, reload=True)