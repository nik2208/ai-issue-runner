"""Adapter for Google Antigravity Python SDK (agy)."""

from pathlib import Path
from typing import Optional
from ai_runner.harnesses.base import AgentHarness, LogCallback
from ai_runner.types import StructuredPlan
from ai_runner.engine.guard import LoopGuard

class AgyHarness(AgentHarness):
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

        try:
            from google.antigravity import Agent, LocalAgentConfig, CapabilitiesConfig
            await log("🌟 Spawning Google Antigravity Agent runtime...")
            config = LocalAgentConfig(
                system_instructions=(
                    "You are executing an autonomous task under a strict acceptance criteria guard.\n"
                    f"Task: {plan.title}\n{plan.summary}"
                ),
                capabilities=CapabilitiesConfig(),
            )
            # Run within the Antigravity agent context
            async with Agent(config) as agent:
                prompt = f"Implement task: {plan.title}.\nAcceptance criteria:\n"
                for ac in plan.acceptance_criteria:
                    prompt += f"- {ac.description} (`{ac.command or ac.path}`)\n"
                
                resp = await agent.chat(prompt)
                async for token in resp:
                    pass
                
                # Check acceptance criteria upon completion
                can_exit, feedback, _ = await guard.evaluate_exit()
                if can_exit:
                    await log(f"✅ Antigravity completed: {feedback}")
                    return True
                else:
                    await log(f"⚠️ Acceptance criteria check failed: {feedback}")
                    return False
        except ImportError:
            await log("⚠️ `google-antigravity` package not available, falling back to NativeHarness.")
            from ai_runner.harnesses.native import NativeHarness
            native = NativeHarness(self.workspace_path)
            return await native.run_plan(plan, on_log=on_log)
