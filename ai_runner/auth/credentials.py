"""Credential management, retrieval, and auto-refresh."""

import os
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional
from ai_runner.config import load_credentials, save_credentials, get_data_dir
from ai_runner.types import AuthStatus
from ai_runner.auth.oauth import oauth_manager

class CredentialStore:
    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or get_data_dir()

    def get_all(self) -> Dict[str, Any]:
        return load_credentials(self.data_dir)

    def get_provider(self, provider: str) -> Dict[str, Any]:
        creds = self.get_all()
        provider_data = creds.get(provider.lower(), {})
        
        # Check standard environment variables as fallback
        if not provider_data:
            if provider.lower() == "anthropic" and os.getenv("ANTHROPIC_API_KEY"):
                return {"api_key": os.getenv("ANTHROPIC_API_KEY"), "mode": "api_key"}
            if provider.lower() in ("openai", "codex") and os.getenv("OPENAI_API_KEY"):
                return {"api_key": os.getenv("OPENAI_API_KEY"), "mode": "api_key"}
            if provider.lower() == "google" and os.getenv("GEMINI_API_KEY"):
                return {"api_key": os.getenv("GEMINI_API_KEY"), "mode": "api_key"}
            
            # Check ~/.gemini/oauth_creds.json as fallback for Google Gemini (Shunt compatibility)
            gemini_creds = Path.home() / ".gemini" / "oauth_creds.json"
            if provider.lower() == "google" and gemini_creds.exists():
                try:
                    with open(gemini_creds, "r", encoding="utf-8") as f:
                        g_data = json.load(f)
                        return {
                            "access_token": g_data.get("access_token"),
                            "refresh_token": g_data.get("refresh_token"),
                            "id_token": g_data.get("id_token"),
                            "mode": "oauth"
                        }
                except Exception:
                    pass
                    
        return provider_data

    def set_provider(self, provider: str, data: Dict[str, Any]) -> None:
        creds = self.get_all()
        creds[provider.lower()] = data
        save_credentials(creds, self.data_dir)

    def remove_provider(self, provider: str) -> None:
        creds = self.get_all()
        if provider.lower() in creds:
            del creds[provider.lower()]
            save_credentials(creds, self.data_dir)

    def get_status(self, provider: str) -> AuthStatus:
        data = self.get_provider(provider)
        if not data:
            return AuthStatus(provider=provider, authenticated=False, auth_mode="none")

        if data.get("api_key"):
            return AuthStatus(provider=provider, authenticated=True, auth_mode="api_key")

        if data.get("access_token"):
            exp = None
            if "expires_in" in data and "obtained_at" in data:
                exp = data["obtained_at"] + data["expires_in"]
            return AuthStatus(
                provider=provider,
                authenticated=True,
                auth_mode="oauth",
                user_email=data.get("email"),
                expires_at=exp
            )

        return AuthStatus(provider=provider, authenticated=False, auth_mode="none")

    async def get_valid_google_token(self) -> Optional[str]:
        """Returns a valid Google access token, refreshing if needed."""
        data = self.get_provider("google")
        if not data:
            return None

        # Direct API key
        if data.get("api_key"):
            return data["api_key"]

        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        obtained_at = data.get("obtained_at", 0)
        expires_in = data.get("expires_in", 3600)

        # Check if expired or about to expire (within 60s)
        now = time.time()
        if access_token and (now < obtained_at + expires_in - 60):
            return access_token

        # Needs refresh
        if refresh_token:
            try:
                new_tokens = await oauth_manager.refresh_google_token(refresh_token)
                data["access_token"] = new_tokens["access_token"]
                data["obtained_at"] = new_tokens.get("obtained_at", time.time())
                if "expires_in" in new_tokens:
                    data["expires_in"] = new_tokens["expires_in"]
                self.set_provider("google", data)
                return data["access_token"]
            except Exception:
                # If refresh fails, return current token if exists
                return access_token

        return access_token

credential_store = CredentialStore()
