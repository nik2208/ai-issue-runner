import pytest
import asyncio
from ai_runner.auth.oauth import generate_pkce_pair, OAuthManager
from ai_runner.auth.interceptor import CliLinkInterceptor
from ai_runner.auth.credentials import CredentialStore

def test_pkce_generation():
    verifier, challenge = generate_pkce_pair()
    assert len(verifier) >= 43
    assert len(challenge) >= 43
    # S256 challenge should not end with padding '='
    assert not challenge.endswith("=")
    assert " " not in verifier and " " not in challenge

def test_google_auth_url_creation():
    mgr = OAuthManager()
    url, state = mgr.create_google_auth_url("http://127.0.0.1:4242/auth/callback")
    assert "accounts.google.com" in url
    assert "code_challenge=" in url
    assert f"state={state}" in url
    assert state in mgr.pending_states
    assert mgr.pending_states[state]["redirect_uri"] == "http://127.0.0.1:4242/auth/callback"

@pytest.mark.asyncio
async def test_link_interceptor_detection():
    interceptor = CliLinkInterceptor()
    detected = []

    async def on_link(url: str):
        detected.append(url)

    interceptor.register_callback(on_link)

    # Line with normal text
    res = await interceptor.inspect_line("Starting build process...")
    assert res is None
    assert len(detected) == 0

    # Line with auth URL
    auth_line = "Please authorize by visiting: https://accounts.google.com/o/oauth2/v2/auth?client_id=123"
    res2 = await interceptor.inspect_line(auth_line)
    assert res2 == "https://accounts.google.com/o/oauth2/v2/auth?client_id=123"
    assert len(detected) == 1
    assert interceptor.latest_url == res2

def test_credential_store(tmp_path, monkeypatch):
    store = CredentialStore(data_dir=tmp_path)
    
    # Initially none
    status = store.get_status("anthropic")
    assert status.authenticated is False

    # Store API key
    store.set_provider("anthropic", {"api_key": "sk-ant-test1234"})
    status2 = store.get_status("anthropic")
    assert status2.authenticated is True
    assert status2.auth_mode == "api_key"

    # Store OAuth token
    store.set_provider("google", {
        "access_token": "ya29.test",
        "refresh_token": "1//test",
        "email": "user@example.com",
        "expires_in": 3600,
        "obtained_at": 1000000.0
    })
    status_g = store.get_status("google")
    assert status_g.authenticated is True
    assert status_g.auth_mode == "oauth"
    assert status_g.user_email == "user@example.com"
