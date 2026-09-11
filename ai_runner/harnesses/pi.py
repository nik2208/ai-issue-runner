"""Subprocess bridge adapter for Pi-Agent (earendil-works/pi)."""

import os
import sys
import asyncio
from pathlib import Path
from typing import Optional
from ai_runner.harnesses.base import AgentHarness, LogCallback
from ai_runner.types import StructuredPlan
from ai_runner.engine.guard import LoopGuard
from ai_runner.config import load_config, load_credentials


class PiHarness(AgentHarness):
    def __init__(self, workspace_path: str | Path):
        super().__init__(workspace_path)

    def _build_env(self) -> dict:
        env = os.environ.copy()
        creds = load_credentials()

        anthropic_key = creds.get("anthropic", {}).get("api_key")
        openai_key = creds.get("openai", {}).get("api_key")
        gemini_key = creds.get("google", {}).get("api_key")

        if anthropic_key and "ANTHROPIC_API_KEY" not in env:
            env["ANTHROPIC_API_KEY"] = anthropic_key
        if openai_key and "OPENAI_API_KEY" not in env:
            env["OPENAI_API_KEY"] = openai_key
        if gemini_key and "GEMINI_API_KEY" not in env:
            env["GEMINI_API_KEY"] = gemini_key

        # Subprocess isolation & python configuration
        venv_bin = Path(sys.prefix) / "bin"
        if venv_bin.exists():
            env["PATH"] = f"{str(venv_bin)}:{env.get('PATH', '')}"
        
        current_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            f"{str(self.workspace_path)}:{current_pythonpath}"
            if current_pythonpath
            else str(self.workspace_path)
        )
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return env

    async def run_plan(
        self,
        plan: StructuredPlan,
        on_log: Optional[LogCallback] = None
    ) -> bool:
        guard = LoopGuard(plan, self.workspace_path)

        async def log(msg: str):
            if on_log:
                await on_log(msg)

        env = self._build_env()

        initial_prompt = (
            f"Goal: {plan.title}\n{plan.summary}\n\n"
            f"Acceptance Criteria to satisfy:\n"
        )
        for ac in plan.acceptance_criteria:
            initial_prompt += f"- [{ac.id}] {ac.description} (Command/Target: `{ac.command or ac.path}`)\n"

        current_prompt = initial_prompt

        await log(f"🚀 Launching Pi-agent harness for task: {plan.task_id} ({plan.title})")

        while guard.iteration < guard.max_iterations:
            await log(f"🔄 Pi-agent iteration {guard.iteration + 1}/{guard.max_iterations}...")

            cmd = ["pi", "-p", current_prompt, "--mode", "print"]
            if plan.model:
                cmd.extend(["--model", plan.model])

            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=str(self.workspace_path),
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                out_str = stdout.decode("utf-8", errors="replace")
                err_str = stderr.decode("utf-8", errors="replace")

                if out_str:
                    preview = out_str.strip()
                    if len(preview) > 500:
                        preview = preview[:500] + "... [truncated]"
                    await log(f"🤖 Pi-agent: {preview}")

                if proc.returncode != 0:
                    await log(f"⚠️ Pi-agent exited with code {proc.returncode}: {err_str[:300]}")

            except FileNotFoundError:
                await log("⚠️ `pi` binary (@earendil-works/pi-coding-agent) not found in PATH.")
                await log("🔄 Falling back to NativeHarness...")
                from ai_runner.harnesses.native import NativeHarness
                native = NativeHarness(self.workspace_path)
                return await native.run_plan(plan, on_log=on_log)

            can_exit, feedback, results = await guard.evaluate_exit()
            all_passed = all(r.passed for r, c in zip(results, plan.acceptance_criteria) if c.critical)

            if all_passed:
                await log(f"🎉 All acceptance criteria passed! {feedback}")
                return True

            if guard.iteration >= guard.max_iterations:
                await log(f"🛑 Reached maximum iterations ({guard.max_iterations}) without satisfying all criteria.")
                return False

            await log(f"⚠️ Iteration {guard.iteration}/{guard.max_iterations}: Criteria not met. Re-prompting Pi-agent with diagnostics...")
            current_prompt = (
                f"Goal: {plan.title}\n"
                f"The previous attempt failed Acceptance Criteria verification:\n\n"
                f"{feedback}\n\n"
                f"Please inspect the errors above and modify the codebase until the criteria are satisfied."
            )

        return False
