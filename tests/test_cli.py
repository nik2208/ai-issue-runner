from typer.testing import CliRunner
from ai_runner.cli import app
from ai_runner.config import export_auth_bundle

runner = CliRunner()

def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Decentralized AI Issue Runner" in result.stdout

def test_cli_status():
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "Google" in result.stdout
    assert "Anthropic" in result.stdout

def test_cli_auth_export_import(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_RUNNER_DATA_DIR", str(tmp_path))
    
    # Import a test bundle
    raw_bundle = "eyJhbnRocm9waWMiOiB7ImFwaV9rZXkiOiAic2stdGVzdCJ9fQ=="
    res_import = runner.invoke(app, ["auth", "import", raw_bundle])
    assert res_import.exit_code == 0
    assert "anthropic" in res_import.stdout

    # Export
    res_export = runner.invoke(app, ["auth", "export"])
    assert res_export.exit_code == 0
    assert raw_bundle in res_export.stdout

def test_cli_login_google():
    result = runner.invoke(app, ["login", "google"])
    assert result.exit_code == 0
    assert "accounts.google.com" in result.stdout
