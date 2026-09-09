"""End-to-end integration test of the Guarded Agentic Loop."""

import pytest
from pathlib import Path
from typing import List, Optional
from ai_runner.types import StructuredPlan, AcceptanceCriterion
from ai_runner.harnesses.native import NativeHarness
from ai_runner.providers.base import BaseProvider, LLMMessage, ToolDefinition, LLMResponse, ToolCall

class ScriptedAgentProvider(BaseProvider):
    """A deterministic provider simulating an agent that initially fails, then self-corrects."""
    def __init__(self):
        super().__init__(default_model="scripted-mock")
        self.step = 0

    async def chat(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[ToolDefinition]] = None,
        model: Optional[str] = None,
        temperature: float = 0.2
    ) -> LLMResponse:
        self.step += 1

        if self.step == 1:
            # Turn 1: Agent prematurely claims it finished without making edits
            return LLMResponse(
                content="I believe the code is already fine. Finishing task.",
                tool_calls=[
                    ToolCall(
                        id="call_premature",
                        name="finish_task",
                        arguments={"summary": "Done without edits"}
                    )
                ]
            )

        elif self.step == 2:
            # Turn 2: Agent sees the rejection feedback from the test failure, and fixes the bug!
            return LLMResponse(
                content="I see the test failed because of subtraction! Let me fix calculator.py.",
                tool_calls=[
                    ToolCall(
                        id="call_fix",
                        name="replace_file_content",
                        arguments={
                            "path": "calculator.py",
                            "target": "return a - b",
                            "replacement": "return a + b"
                        }
                    )
                ]
            )

        elif self.step == 3:
            # Turn 3: Agent invokes finish_task again now that the bug is fixed
            return LLMResponse(
                content="The bug is fixed. Finishing now.",
                tool_calls=[
                    ToolCall(
                        id="call_final",
                        name="finish_task",
                        arguments={"summary": "Fixed operator in calculator.py"}
                    )
                ]
            )

        return LLMResponse(content="Done.")

@pytest.mark.asyncio
async def test_guarded_loop_end_to_end(tmp_path):
    # Setup buggy file
    calc_file = tmp_path / "calculator.py"
    calc_file.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

    # Setup test file
    test_file = tmp_path / "test_calc.py"
    test_file.write_text(
        "from calculator import add\n"
        "def test_addition():\n"
        "    assert add(2, 3) == 5\n",
        encoding="utf-8"
    )

    plan = StructuredPlan(
        task_id="E2E-FIX-001",
        title="Fix calculator addition",
        summary="Ensure calculator.add returns sum",
        acceptance_criteria=[
            AcceptanceCriterion(
                id="pytest_calc",
                description="test_calc.py must pass",
                command="pytest test_calc.py",
                expected_exit_code=0,
                critical=True
            )
        ],
        max_iterations=5,
        harness="native"
    )

    provider = ScriptedAgentProvider()
    harness = NativeHarness(workspace_path=tmp_path, provider=provider)

    logs = []
    async def log_collector(msg: str):
        logs.append(msg)

    success = await harness.run_plan(plan, on_log=log_collector)

    # 1. Verification that loop succeeded overall
    assert success is True

    # 2. Verification that the file was actually corrected by the agent
    fixed_content = calc_file.read_text(encoding="utf-8")
    assert "return a + b" in fixed_content

    # 3. Verification that premature exit was blocked and logged
    log_text = "\n".join(logs)
    assert "COMPLETION REJECTED" in log_text or "AssertionError" in log_text or "Iteration 1" in log_text
    assert "ALL ACCEPTANCE CRITERIA VERIFIED SUCCESSFULLY" in log_text or "Task finished and all acceptance criteria passed!" in log_text
