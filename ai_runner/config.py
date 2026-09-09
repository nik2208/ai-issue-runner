"""Configuration and credential manager."""

import os
import json
import base64
from pathlib import Path
from typing import Dict, Any, Optional
import yaml
from ai_runner.types import RunnerConfig

def get_data_dir(custom_path: Optional[str] = None) -> Path:
    if custom_path:
        p = Path(custom_path).expanduser().resolve()
    else:
        env_dir = os.getenv("AI_RUNNER_DATA_DIR", "~/.ai-runner")
        p = Path(env_dir).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p

def get_config_path(data_dir: Optional[Path] = None) -> Path:
    d = data_dir or get_data_dir()
    return d / "config.yaml"

def get_credentials_path(data_dir: Optional[Path] = None) -> Path:
    d = data_dir or get_data_dir()
    return d / "credentials.json"

def load_config(data_dir: Optional[Path] = None) -> RunnerConfig:
    cfg_file = get_config_path(data_dir)
    if cfg_file.exists():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                return RunnerConfig(**data)
        except Exception:
            return RunnerConfig()
    return RunnerConfig()

def save_config(config: RunnerConfig, data_dir: Optional[Path] = None) -> None:
    cfg_file = get_config_path(data_dir)
    with open(cfg_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(config.model_dump(), f)

def load_credentials(data_dir: Optional[Path] = None) -> Dict[str, Any]:
    # Check env override first (useful for GitHub Actions / CI)
    env_bundle = os.getenv("AI_RUNNER_AUTH")
    if env_bundle:
        try:
            return import_auth_bundle(env_bundle)
        except Exception:
            pass

    cred_file = get_credentials_path(data_dir)
    if cred_file.exists():
        try:
            with open(cred_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_credentials(creds: Dict[str, Any], data_dir: Optional[Path] = None) -> None:
    cred_file = get_credentials_path(data_dir)
    with open(cred_file, "w", encoding="utf-8") as f:
        json.dump(creds, f, indent=2)
    # Ensure secure permissions
    try:
        os.chmod(cred_file, 0o600)
    except Exception:
        pass

def export_auth_bundle(data_dir: Optional[Path] = None) -> str:
    creds = load_credentials(data_dir)
    raw = json.dumps(creds).encode("utf-8")
    return base64.b64encode(raw).decode("utf-8")

def import_auth_bundle(bundle_str: str, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    cleaned = bundle_str.strip()
    try:
        # Try base64 decoding
        raw = base64.b64decode(cleaned)
        creds = json.loads(raw.decode("utf-8"))
    except Exception:
        # Fallback to direct JSON
        creds = json.loads(cleaned)
    
    target_dir = data_dir or get_data_dir()
    save_credentials(creds, target_dir)
    return creds
