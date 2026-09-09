import pytest
from pathlib import Path
from ai_runner.harnesses.native import NativeHarness
from ai_runner.types import StructuredPlan, AcceptanceCriterion
from ai_runner.engine.guard import LoopGuard
from ai_runner.providers.base import ToolCall, LLMMessage

@pytest.mark.asyncio
async def test_native_harness_file_tools(tmp_path):
    harness = NativeHarness(workspace_path=tmp_path)
    guard = LoopGuard(
        StructuredPlan(task_id="t1", title="test", summary="", acceptance_criteria=[]),
        workspace_path=tmp_path
    )

    # 1. Write file
    tc_write = ToolCall(
        id="tc1",
        name="write_file",
        arguments={"path": "src/app.py", "content": "print('hello world')\n"}
    )
    out_w, _ = await harness.execute_tool(tc_write, guard)
    assert "Successfully wrote" in out_w
    assert (tmp_path / "src/app.py").exists()

    # 2. Read file
    tc_read = ToolCall(
        id="tc2",
        name="read_file",
        arguments={"path": "src/app.py", "start_line": 1, "end_line": 1}
    )
    out_r, _ = await harness.execute_tool(tc_read, guard)
    assert "1: print('hello world')" in out_r

    # 3. Replace file content
    tc_repl = ToolCall(
        id="tc3",
        name="replace_file_content",
        arguments={"path": "src/app.py", "target": "hello world", "replacement": "bonjour le monde"}
    )
    out_rep, _ = await harness.execute_tool(tc_repl, guard)
    assert "Successfully replaced" in out_rep
    assert (tmp_path / "src/app.py").read_text() == "print('bonjour le monde')\n"

    # 4. Run bash
    tc_bash = ToolCall(
        id="tc4",
        name="run_bash",
        arguments={"command": "python3 src/app.py"}
    )
    out_b, _ = await harness.execute_tool(tc_bash, guard)
    assert "bonjour le monde" in out_b

@pytest.mark.asyncio
async def test_native_harness_path_safety(tmp_path):
    harness = NativeHarness(workspace_path=tmp_path)
    guard = LoopGuard(
        StructuredPlan(task_id="t1", title="test", summary="", acceptance_criteria=[]),
        workspace_path=tmp_path
    )

    tc_unsafe = ToolCall(
        id="tc_bad",
        name="write_file",
        arguments={"path": "../../etc/evil.txt", "content": "bad"}
    )
    out, _ = await harness.execute_tool(tc_unsafe, guard)
    assert "outside workspace" in out

def test_context_compaction(tmp_path):
    harness = NativeHarness(workspace_path=tmp_path)
    msgs = [
        LLMMessage(role="system", content="System"),
        LLMMessage(role="user", content="Plan"),
        LLMMessage(role="assistant", content="Running tool"),
        LLMMessage(role="tool", content="A" * 1000, tool_call_id="call1"),
        LLMMessage(role="assistant", content="Running another tool"),
        LLMMessage(role="tool", content="B" * 1000, tool_call_id="call2"),
        LLMMessage(role="assistant", content="Running 3rd tool"),
        LLMMessage(role="tool", content="C" * 1000, tool_call_id="call3"),
        LLMMessage(role="assistant", content="Running 4th tool"),
        LLMMessage(role="tool", content="D" * 1000, tool_call_id="call4"),
    ]
    compacted = harness.compact_history(msgs, max_chars=500)
    assert len(compacted) == len(msgs)
    # Check that older tool messages have truncation marker
    assert "...[truncated old tool output]..." in compacted[3].content
