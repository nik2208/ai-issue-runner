"""Provider router and resolver (inspired by Shunt)."""

from typing import Optional, Tuple
from ai_runner.auth.credentials import credential_store, CredentialStore
from ai_runner.providers.base import BaseProvider
from ai_runner.providers.google import GoogleProvider
from ai_runner.providers.anthropic import AnthropicProvider
from ai_runner.providers.openai import OpenAIProvider
from ai_runner.providers.ollama import OllamaProvider

class ProviderRouter:
    def __init__(self, store: Optional[CredentialStore] = None):
        self.store = store or credential_store

    def infer_provider_and_model(self, model_or_provider: Optional[str] = None) -> Tuple[str, str]:
        """Infers provider name and normalized model id."""
        if not model_or_provider:
            return "google", "gemini-2.5-pro"

        m = model_or_provider.lower().strip()
        if m.startswith("gemini") or m.startswith("google"):
            model = m.split("/")[-1] if "/" in m else m
            return "google", model if model != "google" else "gemini-2.5-pro"

        if m.startswith("claude") or m.startswith("anthropic"):
            model = m.split("/")[-1] if "/" in m else m
            return "anthropic", model if model != "anthropic" else "claude-3-7-sonnet-20250219"

        if m.startswith("gpt") or m.startswith("o1") or m.startswith("o3") or m.startswith("openai") or m == "codex":
            model = m.split("/")[-1] if "/" in m else m
            return "openai", model if model != "openai" else "gpt-4o"

        if m.startswith("ollama") or "qwen" in m or "llama" in m or "deepseek" in m:
            model = m.split("/")[-1] if "/" in m else m
            return "ollama", model

        # Default fallback
        return "google", model_or_provider

    async def get_provider(self, model_or_provider: Optional[str] = None) -> BaseProvider:
        """Instantiates and returns the appropriate provider with loaded credentials."""
        prov_name, model_id = self.infer_provider_and_model(model_or_provider)

        if prov_name == "google":
            creds = self.store.get_provider("google")
            token = await self.store.get_valid_google_token()
            if not token:
                raise ValueError("No credentials found for Google provider. Please login or set GEMINI_API_KEY.")
            is_oauth = creds.get("mode") == "oauth" or "ya29." in token or creds.get("refresh_token") is not None
            return GoogleProvider(token_or_key=token, is_oauth=is_oauth, default_model=model_id)

        elif prov_name == "anthropic":
            creds = self.store.get_provider("anthropic")
            key = creds.get("api_key")
            if not key:
                raise ValueError("No credentials found for Anthropic. Please configure API key.")
            return AnthropicProvider(api_key=key, default_model=model_id)

        elif prov_name == "openai":
            creds = self.store.get_provider("openai")
            key = creds.get("api_key")
            if not key:
                raise ValueError("No credentials found for OpenAI. Please configure API key.")
            base_url = creds.get("base_url", "https://api.openai.com/v1/chat/completions")
            return OpenAIProvider(api_key=key, base_url=base_url, default_model=model_id)

        elif prov_name == "ollama":
            creds = self.store.get_provider("ollama")
            host = creds.get("host", "http://127.0.0.1:11434")
            return OllamaProvider(host=host, default_model=model_id)

        raise ValueError(f"Unsupported provider: {prov_name}")

provider_router = ProviderRouter()
