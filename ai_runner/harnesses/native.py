"""Native high-performance agent harness with atomic tools and guarded loop."""

import os
import sys
import re
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from ai_runner.harnesses.base import AgentHarness, LogCallback
from ai_runner.types import StructuredPlan
from ai_runner.providers.base import BaseProvider, LLMMessage, ToolDefinition, ToolCall
from ai_runner.providers.router import provider_router
from ai_runner.engine.guard import LoopGuard

class NativeHarness(AgentHarness):
    def __init__(self, workspace_path: str | Path, provider: Optional[BaseProvider] = None):
        super().__init__(workspace_path)
        self.provider = provider
        self.tool_definitions = self._build_tool_definitions()

    def _build_env(self) -> dict:
        env = os.environ.copy()
        venv_bin = Path(sys.prefix) / "bin"
        if venv_bin.exists():
            env["PATH"] = f"{str(venv_bin)}:{env.get('PATH', '')}"
        current_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{str(self.workspace_path)}:{current_pythonpath}" if current_pythonpath else str(self.workspace_path)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return env

    def _build_tool_definitions(self) -> List[ToolDefinition]:
        return [
            ToolDefinition(
                name="read_file",
                description="Read contents of a file with optional line ranges.",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative path to file"},
                        "start_line": {"type": "integer", "description": "1-indexed start line"},
                        "end_line": {"type": "integer", "description": "1-indexed end line"}
                    },
                    "required": ["path"]
                }
            ),
            ToolDefinition(
                name="write_file",
                description="Write or overwrite full content to a file.",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative path to file"},
                        "content": {"type": "string", "description": "Full file content"}
                    },
                    "required": ["path", "content"]
                }
            ),
            ToolDefinition(
                name="replace_file_content",
                description="Replace an exact snippet in an existing file.",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative path to file"},
                        "target": {"type": "string", "description": "Exact text to replace"},
                        "replacement": {"type": "string", "description": "New replacement text"}
                    },
                    "required": ["path", "target", "replacement"]
                }
            ),
            ToolDefinition(
                name="run_bash",
                description="Execute a bash shell command in the workspace directory.",
                parameters={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Command line to execute"}
                    },
                    "required": ["command"]
                }
            ),
            ToolDefinition(
                name="finish_task",
                description="Signal task completion. Triggers Acceptance Criteria verification.",
                parameters={
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string", "description": "Summary of changes made"}
                    },
                    "required": ["summary"]
                }
            )
        ]

    def _resolve_safe_path(self, rel_path: str) -> Path:
        target = (self.workspace_path / rel_path).resolve()
        if not str(target).startswith(str(self.workspace_path)):
            raise PermissionError(f"Access denied: Path '{rel_path}' is outside workspace.")
        return target

    async def execute_tool(self, tool_call: ToolCall, guard: LoopGuard) -> Tuple[str, bool]:
        """Executes a single tool call. Returns (output_str, is_finish_attempt_and_passed)."""
        name = tool_call.name
        args = tool_call.arguments

        try:
            if name == "read_file":
                p = self._resolve_safe_path(args.get("path", ""))
                if not p.exists():
                    return f"Error: File '{args.get('path')}' does not exist.", False
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
                start = max(1, args.get("start_line", 1)) - 1
                end = args.get("end_line", len(lines))
                sliced = lines[start:end]
                numbered = [f"{i+start+1}: {line}" for i, line in enumerate(sliced)]
                return "\n".join(numbered), False

            elif name == "write_file":
                p = self._resolve_safe_path(args.get("path", ""))
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(args.get("content", ""), encoding="utf-8")
                return f"Successfully wrote {len(args.get('content', ''))} characters to {args.get('path')}.", False

            elif name == "replace_file_content":
                p = self._resolve_safe_path(args.get("path", ""))
                if not p.exists():
                    return f"Error: File '{args.get('path')}' not found.", False
                text = p.read_text(encoding="utf-8")
                target = args.get("target", "")
                replacement = args.get("replacement", "")
                if target not in text:
                    return f"Error: Target text not found in '{args.get('path')}'.", False
                new_text = text.replace(target, replacement, 1)
                p.write_text(new_text, encoding="utf-8")
                return f"Successfully replaced content in {args.get('path')}.", False

            elif name == "run_bash":
                cmd = args.get("command", "")
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    cwd=str(self.workspace_path),
                    env=self._build_env(),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=120.0)
                stdout = stdout_b.decode("utf-8", errors="replace")
                stderr = stderr_b.decode("utf-8", errors="replace")
                output = f"Exit code: {proc.returncode}\n"
                if stdout:
                    output += f"Stdout:\n{stdout}\n"
                if stderr:
                    output += f"Stderr:\n{stderr}\n"
                return output, False

            elif name == "finish_task":
                summary = args.get("summary", "")
                can_exit, feedback, _ = await guard.evaluate_exit(summary)
                if can_exit:
                    return f"✅ SUCCESS: {feedback}", True
                else:
                    return feedback, False

            return f"Unknown tool: {name}", False

        except Exception as e:
            return f"Tool execution error ({name}): {str(e)}", False

    def compact_history(self, messages: List[LLMMessage], max_chars: int = 40000) -> List[LLMMessage]:
        """Compacts older tool execution outputs to preserve token context window."""
        total_len = sum(len(m.content) for m in messages)
        if total_len <= max_chars or len(messages) <= 6:
            return messages

        # Preserve system prompt and first user message
        compacted = [messages[0], messages[1]]
        # Compact middle tool messages
        for msg in messages[2:-4]:
            if msg.role == "tool" and len(msg.content) > 300:
                short_content = msg.content[:150] + "\n...[truncated old tool output]...\n" + msg.content[-100:]
                compacted.append(LLMMessage(role=msg.role, content=short_content, tool_call_id=msg.tool_call_id, name=msg.name))
            else:
                compacted.append(msg)

        # Append last 4 messages intact
        compacted.extend(messages[-4:])
        return compacted

    async def run_plan(
        self,
        plan: StructuredPlan,
        on_log: Optional[LogCallback] = None
    ) -> bool:
        prov = self.provider or await provider_router.get_provider(plan.model or plan.provider)
        guard = LoopGuard(plan, self.workspace_path)

        async def log(msg: str):
            if on_log:
                await on_log(msg)

        system_instruction = (
            "You are an autonomous AI coding runner. Your task is to execute the following plan "
            "and ensure all Acceptance Criteria pass.\n"
            "You have tools to read, write, and patch files, and to run bash commands.\n"
            "When you believe the task is fully accomplished and tests pass, invoke `finish_task`.\n"
            "NOTE: The environment strictly verifies your changes against Acceptance Criteria. "
            "If any criterion fails, completion will be rejected and you will be forced to fix it."
        )

        plan_prompt = f"Goal: {plan.title}\nSummary: {plan.summary}\n\nAcceptance Criteria to satisfy:\n"
        for ac in plan.acceptance_criteria:
            plan_prompt += f"- [{ac.id}] {ac.description} (Command: `{ac.command or ac.path}`)\n"

        messages: List[LLMMessage] = [
            LLMMessage(role="system", content=system_instruction),
            LLMMessage(role="user", content=plan_prompt)
        ]

        await log(f"🚀 Starting guarded execution loop for task: {plan.task_id} ({plan.title})")

        while guard.iteration < guard.max_iterations:
            messages = self.compact_history(messages)
            await log(f"🧠 Agent reasoning (Iteration {guard.iteration + 1}/{guard.max_iterations})...")

            response = await prov.chat(
                messages=messages,
                tools=self.tool_definitions,
                model=plan.model,
                temperature=0.1
            )

            # Record assistant turn
            messages.append(LLMMessage(
                role="assistant",
                content=response.content,
                tool_calls=response.tool_calls
            ))

            if response.content:
                await log(f"🤖 Agent: {response.content}")

            if not response.tool_calls:
                # If agent stopped without calling finish_task, remind it
                await log("⚠️ Agent responded without tool calls. Probing acceptance criteria...")
                can_exit, feedback, _ = await guard.evaluate_exit()
                if can_exit:
                    await log(f"🎉 {feedback}")
                    return True
                messages.append(LLMMessage(role="user", content=feedback))
                continue

            # Execute tool calls
            for tc in response.tool_calls:
                await log(f"🔧 Tool: {tc.name}({tc.arguments})")
                out, passed = await self.execute_tool(tc, guard)
                
                messages.append(LLMMessage(
                    role="tool",
                    content=out,
                    tool_call_id=tc.id,
                    name=tc.name
                ))

                if passed:
                    await log("🎉 Task finished and all acceptance criteria passed!")
                    return True

        await log("🛑 Max iterations reached without satisfying all acceptance criteria.")
        return False
