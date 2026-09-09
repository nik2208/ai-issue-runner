"""Acceptance criteria verification engine."""

import os
import sys
import re
import time
import asyncio
from pathlib import Path
from typing import List, Optional
from ai_runner.types import AcceptanceCriterion, VerificationResult

class AcceptanceVerifier:
    def __init__(self, workspace_path: str | Path):
        self.workspace_path = Path(workspace_path).resolve()

    def _build_env(self) -> dict:
        env = os.environ.copy()
        venv_bin = Path(sys.prefix) / "bin"
        if venv_bin.exists():
            env["PATH"] = f"{str(venv_bin)}:{env.get('PATH', '')}"
        current_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{str(self.workspace_path)}:{current_pythonpath}" if current_pythonpath else str(self.workspace_path)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return env

    async def verify_command(self, criterion: AcceptanceCriterion) -> VerificationResult:
        if not criterion.command:
            return VerificationResult(
                criterion_id=criterion.id,
                passed=False,
                message="Command not specified"
            )

        start_time = time.time()
        try:
            proc = await asyncio.create_subprocess_shell(
                criterion.command,
                cwd=str(self.workspace_path),
                env=self._build_env(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=float(criterion.timeout_seconds)
            )
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            exit_code = proc.returncode
            duration = (time.time() - start_time) * 1000

            passed = (exit_code == criterion.expected_exit_code)
            msg = f"Command exited with {exit_code} (expected {criterion.expected_exit_code})"
            return VerificationResult(
                criterion_id=criterion.id,
                passed=passed,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                message=msg,
                duration_ms=duration
            )

        except asyncio.TimeoutError:
            duration = (time.time() - start_time) * 1000
            try:
                proc.kill()
            except Exception:
                pass
            return VerificationResult(
                criterion_id=criterion.id,
                passed=False,
                exit_code=-1,
                stderr=f"Command timed out after {criterion.timeout_seconds}s",
                message=f"Timeout after {criterion.timeout_seconds}s",
                duration_ms=duration
            )
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return VerificationResult(
                criterion_id=criterion.id,
                passed=False,
                exit_code=-1,
                stderr=str(e),
                message=f"Execution error: {str(e)}",
                duration_ms=duration
            )

    async def verify_file_exists(self, criterion: AcceptanceCriterion) -> VerificationResult:
        start_time = time.time()
        if not criterion.path:
            return VerificationResult(
                criterion_id=criterion.id,
                passed=False,
                message="File path not specified"
            )

        target = self.workspace_path / criterion.path
        passed = target.exists()
        duration = (time.time() - start_time) * 1000
        msg = f"File {criterion.path} {'exists' if passed else 'does not exist'}"
        return VerificationResult(
            criterion_id=criterion.id,
            passed=passed,
            exit_code=0 if passed else 1,
            message=msg,
            duration_ms=duration
        )

    async def verify_regex_match(self, criterion: AcceptanceCriterion) -> VerificationResult:
        start_time = time.time()
        if not criterion.path or not criterion.pattern:
            return VerificationResult(
                criterion_id=criterion.id,
                passed=False,
                message="Path or pattern not specified"
            )

        target = self.workspace_path / criterion.path
        if not target.exists():
            return VerificationResult(
                criterion_id=criterion.id,
                passed=False,
                exit_code=1,
                message=f"Target file {criterion.path} does not exist",
                duration_ms=(time.time() - start_time) * 1000
            )

        try:
            content = target.read_text(encoding="utf-8")
            matched = bool(re.search(criterion.pattern, content))
            duration = (time.time() - start_time) * 1000
            return VerificationResult(
                criterion_id=criterion.id,
                passed=matched,
                exit_code=0 if matched else 1,
                message=f"Pattern {'matched' if matched else 'not matched'} in {criterion.path}",
                duration_ms=duration
            )
        except Exception as e:
            return VerificationResult(
                criterion_id=criterion.id,
                passed=False,
                exit_code=1,
                message=str(e),
                duration_ms=(time.time() - start_time) * 1000
            )

    async def verify_criterion(self, criterion: AcceptanceCriterion) -> VerificationResult:
        if criterion.type == "command":
            return await self.verify_command(criterion)
        elif criterion.type == "file_exists":
            return await self.verify_file_exists(criterion)
        elif criterion.type == "regex_match":
            return await self.verify_regex_match(criterion)
        else:
            return VerificationResult(
                criterion_id=criterion.id,
                passed=False,
                message=f"Unknown criterion type: {criterion.type}"
            )

    async def verify_all(self, criteria: List[AcceptanceCriterion]) -> List[VerificationResult]:
        results = []
        for c in criteria:
            res = await self.verify_criterion(c)
            results.append(res)
        return results
