"""Auth endpoints — API key retrieval for local frontend."""
from fastapi import APIRouter, Request, HTTPException
from app.middleware.auth import get_or_create_api_key

router = APIRouter()


@router.get("/key")
async def get_api_key(request: Request):
    """
    Return the server API key.
    Restricted to localhost connections only for security.
    """
    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "localhost", "::1"):
        raise HTTPException(status_code=403, detail="此端点仅限本地访问")
    return {"api_key": get_or_create_api_key()}
