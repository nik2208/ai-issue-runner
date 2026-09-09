import os
import json
from pathlib import Path
from ai_runner.config import (
    load_config,
    save_config,
    load_credentials,
    save_credentials,
    export_auth_bundle,
    import_auth_bundle,
)
from ai_runner.types import RunnerConfig

def test_config_save_load(tmp_path):
    cfg = RunnerConfig(host="0.0.0.0", port=8080, default_provider="anthropic")
    save_config(cfg, data_dir=tmp_path)
    
    loaded = load_config(data_dir=tmp_path)
    assert loaded.host == "0.0.0.0"
    assert loaded.port == 8080
    assert loaded.default_provider == "anthropic"

def test_credentials_save_load_and_bundle(tmp_path):
    creds = {
        "google": {"access_token": "token123", "refresh_token": "ref456"},
        "anthropic": {"api_key": "sk-ant-test"}
    }
    save_credentials(creds, data_dir=tmp_path)
    
    loaded = load_credentials(data_dir=tmp_path)
    assert loaded["google"]["access_token"] == "token123"
    assert loaded["anthropic"]["api_key"] == "sk-ant-test"

    bundle = export_auth_bundle(data_dir=tmp_path)
    assert isinstance(bundle, str)

    # Test import in another clean directory
    other_path = tmp_path / "other"
    other_path.mkdir()
    imported = import_auth_bundle(bundle, data_dir=other_path)
    assert imported["google"]["refresh_token"] == "ref456"
    assert (other_path / "credentials.json").exists()
