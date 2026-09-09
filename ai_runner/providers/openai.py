"""OpenAI / Codex provider driver."""

import json
from typing import List, Optional, Dict, Any
import httpx
from ai_runner.providers.base import BaseProvider, LLMMessage, ToolDefinition, LLMResponse, ToolCall

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

class OpenAIProvider(BaseProvider):
    def __init__(self, api_key: str, base_url: str = OPENAI_API_URL, default_model: str = "gpt-4o"):
        super().__init__(default_model=default_model)
        self.api_key = api_key
        self.base_url = base_url

    def _convert_messages(self, messages: List[LLMMessage]) -> List[Dict[str, Any]]:
        converted = []
        for msg in messages:
            item: Dict[str, Any] = {"role": msg.role, "content": msg.content}
            if msg.tool_calls:
                item["tool_calls"] = [{
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments)
                    }
                } for tc in msg.tool_calls]
            if msg.tool_call_id:
                item["tool_call_id"] = msg.tool_call_id
            if msg.name:
                item["name"] = msg.name
            converted.append(item)
        return converted

    async def chat(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[ToolDefinition]] = None,
        model: Optional[str] = None,
        temperature: float = 0.2
    ) -> LLMResponse:
        model_name = model or self.default_model
        body: Dict[str, Any] = {
            "model": model_name,
            "messages": self._convert_messages(messages),
            "temperature": temperature
        }

        if tools:
            body["tools"] = [{
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters
                }
            } for t in tools]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(self.base_url, headers=headers, json=body)
            if resp.status_code != 200:
                raise RuntimeError(f"OpenAI error ({resp.status_code}): {resp.text}")

            data = resp.json()
            choice = data.get("choices", [{}])[0]
            msg = choice.get("message", {})
            text_content = msg.get("content") or ""
            raw_tool_calls = msg.get("tool_calls") or []

            tool_calls = []
            for tc in raw_tool_calls:
                fn = tc.get("function", {})
                args = {}
                try:
                    args = json.loads(fn.get("arguments", "{}"))
                except Exception:
                    pass
                tool_calls.append(ToolCall(
                    id=tc.get("id", "call_unknown"),
                    name=fn.get("name", ""),
                    arguments=args
                ))

            finish_reason = choice.get("finish_reason", "stop")
            return LLMResponse(
                content=text_content,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
                usage=data.get("usage", {})
            )
