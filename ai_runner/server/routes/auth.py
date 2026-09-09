"""Auth endpoints for Web UI and OAuth callbacks."""

from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Dict, Any
from ai_runner.auth.oauth import oauth_manager
from ai_runner.auth.credentials import credential_store

router = APIRouter(prefix="/auth", tags=["auth"])

class ApiKeyPayload(BaseModel):
    provider: str
    api_key: str

@router.get("/status")
async def get_all_auth_status():
    providers = ["google", "anthropic", "openai", "ollama"]
    return {p: credential_store.get_status(p).model_dump() for p in providers}

@router.get("/login/{provider}")
async def initiate_oauth(provider: str, request: Request):
    if provider.lower() != "google":
        raise HTTPException(status_code=400, detail=f"OAuth not supported for {provider}. Use API key.")
    
    # Base callback URL using current host
    host = request.headers.get("host", "127.0.0.1:4242")
    scheme = request.url.scheme
    redirect_uri = f"{scheme}://{host}/auth/callback"
    
    auth_url, state = oauth_manager.create_google_auth_url(redirect_uri)
    return {"auth_url": auth_url, "state": state}

@router.get("/callback")
async def oauth_callback(code: str = Query(...), state: str = Query(...)):
    try:
        tokens = await oauth_manager.exchange_code(code, state)
        credential_store.set_provider("google", {
            "access_token": tokens.get("access_token"),
            "refresh_token": tokens.get("refresh_token"),
            "id_token": tokens.get("id_token"),
            "expires_in": tokens.get("expires_in", 3600),
            "obtained_at": tokens.get("obtained_at"),
            "mode": "oauth"
        })
        
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authentication Successful</title>
            <style>
                body { font-family: system-ui, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; background: #0f172a; color: #f8fafc; }
                .card { background: #1e293b; padding: 2rem; border-radius: 12px; border: 1px solid #334155; text-align: center; max-width: 400px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
                h1 { color: #10b981; font-size: 1.5rem; margin-bottom: 0.5rem; }
                p { color: #94a3b8; font-size: 0.95rem; }
            </style>
        </head>
        <body>
            <div class="card">
                <h1>✅ Authentication Successful!</h1>
                <p>Your Google AI credentials have been saved to the runner. You can now close this tab and return to the dashboard.</p>
                <script>
                    setTimeout(() => { window.close(); }, 2500);
                </script>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OAuth exchange failed: {str(e)}")

@router.post("/apikey")
async def set_api_key(payload: ApiKeyPayload):
    credential_store.set_provider(payload.provider, {
        "api_key": payload.api_key.strip(),
        "mode": "api_key"
    })
    return {"status": "ok", "provider": payload.provider, "auth_mode": "api_key"}

@router.delete("/provider/{provider}")
async def remove_provider_creds(provider: str):
    credential_store.remove_provider(provider)
    return {"status": "ok", "removed": provider}
