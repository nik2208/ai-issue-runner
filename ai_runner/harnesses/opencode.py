"""Subprocess bridge adapter for OpenCode (anomalyco/opencode)."""

import asyncio
from pathlib import Path
from typing import Optional
from ai_runner.harnesses.base import AgentHarness, LogCallback
from ai_runner.types import StructuredPlan
from ai_runner.engine.guard import LoopGuard

class OpenCodeHarness(AgentHarness):
    def __init__(self, workspace_path: str | Path):
        super().__init__(workspace_path)

    async def run_plan(
        self,
        plan: StructuredPlan,
        on_log: Optional[LogCallback] = None
    ) -> bool:
        guard = LoopGuard(plan, self.workspace_path)
        
        async def log(msg: str):
            if on_log:
                await on_log(msg)

        prompt = f"Goal: {plan.title}\n{plan.summary}\nCriteria:\n"
        for ac in plan.acceptance_criteria:
            prompt += f"- {ac.description}\n"

        await log("🚀 Launching OpenCode CLI runner...")
        try:
            proc = await asyncio.create_subprocess_exec(
                "opencode", "run", "--prompt", prompt,
                cwd=str(self.workspace_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                await log(f"⚠️ OpenCode exited with {proc.returncode}")
        except FileNotFoundError:
            await log("⚠️ `opencode` binary not found in PATH, falling back to NativeHarness.")
            from ai_runner.harnesses.native import NativeHarness
            native = NativeHarness(self.workspace_path)
            return await native.run_plan(plan, on_log=on_log)

        can_exit, feedback, _ = await guard.evaluate_exit()
        return can_exit
