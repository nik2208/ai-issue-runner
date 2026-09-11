import os
import pytest
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from ai_runner.harnesses.pi import PiHarness
from ai_runner.harnesses.native import NativeHarness
from ai_runner.types import StructuredPlan, AcceptanceCriterion
from ai_runner.config import save_credentials

@pytest.mark.asyncio
async def test_pi_harness_env_building(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("AI_RUNNER_DATA_DIR", str(data_dir))
    save_credentials({
        "anthropic": {"api_key": "sk-ant-test-123"},
        "openai": {"api_key": "sk-openai-test-456"},
        "google": {"api_key": "gm-test-789"}
    }, data_dir=data_dir)

    harness = PiHarness(workspace_path=tmp_path)
    env = harness._build_env()

    assert env.get("ANTHROPIC_API_KEY") == "sk-ant-test-123"
    assert env.get("OPENAI_API_KEY") == "sk-openai-test-456"
    assert env.get("GEMINI_API_KEY") == "gm-test-789"
    assert env.get("PYTHONDONTWRITEBYTECODE") == "1"
    assert str(tmp_path) in env.get("PYTHONPATH", "")

@pytest.mark.asyncio
async def test_pi_harness_success_run(tmp_path):
    harness = PiHarness(workspace_path=tmp_path)

    plan = StructuredPlan(
        task_id="pi-001",
        title="Create greetings file",
        summary="Create hello.txt with 'Hello Pi'",
        acceptance_criteria=[
            AcceptanceCriterion(
                id="ac1",
                type="regex_match",
                description="hello.txt exists with correct text",
                path="hello.txt",
                pattern="Hello Pi"
            )
        ],
        max_iterations=3,
        harness="pi"
    )

    logs = []
    async def log_cb(msg):
        logs.append(msg)

    # Mock subprocess to write the expected file and exit 0
    async def mock_subprocess(*args, **kwargs):
        (tmp_path / "hello.txt").write_text("Hello Pi\n", encoding="utf-8")
        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"Done creating hello.txt", b""))
        proc.returncode = 0
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess) as mock_exec:
        success = await harness.run_plan(plan, on_log=log_cb)

        assert success is True
        assert (tmp_path / "hello.txt").exists()
        assert any("All acceptance criteria passed" in l for l in logs)
        assert mock_exec.called
        call_args = mock_exec.call_args[0]
        assert call_args[0] == "pi"
        assert "-p" in call_args
        assert "--mode" in call_args
        assert "print" in call_args

@pytest.mark.asyncio
async def test_pi_harness_self_correction(tmp_path):
    harness = PiHarness(workspace_path=tmp_path)

    plan = StructuredPlan(
        task_id="pi-002",
        title="Fix math bug",
        summary="Fix formula in calc.txt to equal 42",
        acceptance_criteria=[
            AcceptanceCriterion(
                id="ac_math",
                type="regex_match",
                description="calc.txt must contain 42",
                path="calc.txt",
                pattern="42"
            )
        ],
        max_iterations=3,
        harness="pi"
    )

    logs = []
    async def log_cb(msg):
        logs.append(msg)

    turn = 0
    captured_prompts = []

    async def mock_subprocess(*args, **kwargs):
        nonlocal turn
        turn += 1
        # Capture prompt argument passed after -p
        cmd_args = list(args)
        if "-p" in cmd_args:
            idx = cmd_args.index("-p")
            captured_prompts.append(cmd_args[idx + 1])

        proc = MagicMock()
        if turn == 1:
            # First turn: write wrong content
            (tmp_path / "calc.txt").write_text("Wrong value: 0\n", encoding="utf-8")
            proc.communicate = AsyncMock(return_value=(b"Created calc.txt with 0", b""))
            proc.returncode = 0
        else:
            # Second turn: fix the content after receiving feedback
            (tmp_path / "calc.txt").write_text("Fixed value: 42\n", encoding="utf-8")
            proc.communicate = AsyncMock(return_value=(b"Fixed calc.txt to 42", b""))
            proc.returncode = 0
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess):
        success = await harness.run_plan(plan, on_log=log_cb)

        assert success is True
        assert turn == 2
        assert len(captured_prompts) == 2
        # Verify second prompt contains the error diagnostic feedback
        assert "failed Acceptance Criteria verification" in captured_prompts[1]
        assert "calc.txt" in captured_prompts[1]
        assert any("Criteria not met. Re-prompting Pi-agent" in l for l in logs)

@pytest.mark.asyncio
async def test_pi_harness_fallback_on_missing_binary(tmp_path):
    harness = PiHarness(workspace_path=tmp_path)

    plan = StructuredPlan(
        task_id="pi-003",
        title="Fallback test",
        summary="Test fallback when pi is not installed",
        acceptance_criteria=[
            AcceptanceCriterion(
                id="ac_empty",
                description="Always pass",
                command="true"
            )
        ],
        max_iterations=2,
        harness="pi"
    )

    logs = []
    async def log_cb(msg):
        logs.append(msg)

    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
        with patch.object(NativeHarness, "run_plan", new_callable=AsyncMock) as mock_native_run:
            mock_native_run.return_value = True
            success = await harness.run_plan(plan, on_log=log_cb)

            assert success is True
            assert mock_native_run.called
            assert any("not found in PATH" in l for l in logs)
            assert any("Falling back to NativeHarness" in l for l in logs)
