"""OAuth2 PKCE generation and provider token exchange."""

import os
import secrets
import hashlib
import base64
import time
from typing import Dict, Tuple, Optional, Any
import httpx

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Default public client ID for desktop/local apps (can be overridden via env)
DEFAULT_GOOGLE_CLIENT_ID = os.getenv(
    "AI_RUNNER_GOOGLE_CLIENT_ID",
    "936475272427-p7vjdfsqf0u8o0q2g0449k5kn22u0r5p.apps.googleusercontent.com" # Google CLI public client
)
DEFAULT_GOOGLE_CLIENT_SECRET = os.getenv("AI_RUNNER_GOOGLE_CLIENT_SECRET", "")

def generate_pkce_pair() -> Tuple[str, str]:
    """Generates a random code_verifier and its SHA256 code_challenge."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
    return verifier, challenge

class OAuthManager:
    def __init__(self):
        # Maps state -> {"verifier": str, "provider": str, "created_at": float}
        self.pending_states: Dict[str, Dict[str, Any]] = {}

    def create_google_auth_url(self, redirect_uri: str) -> Tuple[str, str]:
        """Creates Google OAuth2 PKCE authorization URL and returns (auth_url, state)."""
        verifier, challenge = generate_pkce_pair()
        state = secrets.token_urlsafe(32)
        
        self.pending_states[state] = {
            "verifier": verifier,
            "provider": "google",
            "created_at": time.time(),
            "redirect_uri": redirect_uri
        }

        scopes = [
            "https://www.googleapis.com/auth/generative-language",
            "https://www.googleapis.com/auth/cloud-platform",
            "openid",
            "email",
            "profile"
        ]
        
        params = {
            "client_id": DEFAULT_GOOGLE_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "access_type": "offline",
            "prompt": "consent"
        }
        
        req = httpx.Request("GET", GOOGLE_AUTH_URL, params=params)
        return str(req.url), state

    async def exchange_code(
        self,
        code: str,
        state: str,
        override_client_id: Optional[str] = None,
        override_client_secret: Optional[str] = None
    ) -> Dict[str, Any]:
        """Exchanges an authorization code for access and refresh tokens using PKCE verifier."""
        state_data = self.pending_states.pop(state, None)
        if not state_data:
            raise ValueError(f"Invalid or expired OAuth state: {state}")

        verifier = state_data["verifier"]
        redirect_uri = state_data["redirect_uri"]
        client_id = override_client_id or DEFAULT_GOOGLE_CLIENT_ID
        client_secret = override_client_secret or DEFAULT_GOOGLE_CLIENT_SECRET

        payload = {
            "client_id": client_id,
            "code": code,
            "code_verifier": verifier,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri
        }
        if client_secret:
            payload["client_secret"] = client_secret

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(GOOGLE_TOKEN_URL, data=payload)
            if resp.status_code != 200:
                raise RuntimeError(f"Token exchange failed ({resp.status_code}): {resp.text}")
            
            data = resp.json()
            data["obtained_at"] = time.time()
            return data

    async def refresh_google_token(
        self,
        refresh_token: str,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None
    ) -> Dict[str, Any]:
        """Refreshes a Google access token using the stored refresh_token."""
        cid = client_id or DEFAULT_GOOGLE_CLIENT_ID
        csec = client_secret or DEFAULT_GOOGLE_CLIENT_SECRET
        
        payload = {
            "client_id": cid,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }
        if csec:
            payload["client_secret"] = csec

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(GOOGLE_TOKEN_URL, data=payload)
            if resp.status_code != 200:
                raise RuntimeError(f"Token refresh failed ({resp.status_code}): {resp.text}")
            
            data = resp.json()
            data["obtained_at"] = time.time()
            return data

oauth_manager = OAuthManager()
