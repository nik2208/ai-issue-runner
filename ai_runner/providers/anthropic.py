"""Anthropic Claude Messages provider driver."""

from typing import List, Optional, Dict, Any
import httpx
from ai_runner.providers.base import BaseProvider, LLMMessage, ToolDefinition, LLMResponse, ToolCall

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"

class AnthropicProvider(BaseProvider):
    def __init__(self, api_key: str, default_model: str = "claude-3-7-sonnet-20250219"):
        super().__init__(default_model=default_model)
        self.api_key = api_key

    def _convert_messages(self, messages: List[LLMMessage]) -> tuple[str, List[Dict[str, Any]]]:
        system_prompt = ""
        converted = []

        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content
            elif msg.role == "user":
                converted.append({"role": "user", "content": msg.content})
            elif msg.role == "assistant":
                content_blocks = []
                if msg.content:
                    content_blocks.append({"type": "text", "text": msg.content})
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        content_blocks.append({
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.arguments
                        })
                converted.append({"role": "assistant", "content": content_blocks})
            elif msg.role == "tool":
                converted.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id or "tool_call_unknown",
                        "content": msg.content
                    }]
                })

        return system_prompt, converted

    async def chat(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[ToolDefinition]] = None,
        model: Optional[str] = None,
        temperature: float = 0.2
    ) -> LLMResponse:
        model_name = model or self.default_model
        system_prompt, converted_msgs = self._convert_messages(messages)

        body: Dict[str, Any] = {
            "model": model_name,
            "messages": converted_msgs,
            "max_tokens": 4096,
            "temperature": temperature
        }
        if system_prompt:
            body["system"] = system_prompt

        if tools:
            body["tools"] = [{
                "name": t.name,
                "description": t.description,
                "input_schema": t.parameters
            } for t in tools]

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(ANTHROPIC_API_URL, headers=headers, json=body)
            if resp.status_code != 200:
                raise RuntimeError(f"Anthropic error ({resp.status_code}): {resp.text}")

            data = resp.json()
            text_content = ""
            tool_calls = []

            for block in data.get("content", []):
                if block.get("type") == "text":
                    text_content += block.get("text", "")
                elif block.get("type") == "tool_use":
                    tool_calls.append(ToolCall(
                        id=block.get("id", "call_unknown"),
                        name=block.get("name", ""),
                        arguments=block.get("input", {})
                    ))

            finish_reason = "tool_calls" if tool_calls else "stop"
            return LLMResponse(
                content=text_content,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
                usage=data.get("usage", {})
            )
