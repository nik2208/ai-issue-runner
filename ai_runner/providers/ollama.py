"""Ollama local / LAN LLM provider driver."""

import os
from typing import List, Optional, Dict, Any
import httpx
from ai_runner.providers.base import BaseProvider, LLMMessage, ToolDefinition, LLMResponse, ToolCall

DEFAULT_OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")

class OllamaProvider(BaseProvider):
    def __init__(self, host: str = DEFAULT_OLLAMA_HOST, default_model: str = "qwen2.5-coder:latest"):
        super().__init__(default_model=default_model)
        self.host = host.rstrip("/")

    async def chat(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[ToolDefinition]] = None,
        model: Optional[str] = None,
        temperature: float = 0.2
    ) -> LLMResponse:
        model_name = model or self.default_model
        msgs = [{"role": m.role, "content": m.content} for m in messages]
        
        body: Dict[str, Any] = {
            "model": model_name,
            "messages": msgs,
            "stream": False,
            "options": {"temperature": temperature}
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

        url = f"{self.host}/api/chat"
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=body)
            if resp.status_code != 200:
                raise RuntimeError(f"Ollama error ({resp.status_code}): {resp.text}")

            data = resp.json()
            msg = data.get("message", {})
            text_content = msg.get("content") or ""
            raw_tool_calls = msg.get("tool_calls") or []

            tool_calls = []
            for i, tc in enumerate(raw_tool_calls):
                fn = tc.get("function", {})
                tool_calls.append(ToolCall(
                    id=f"call_ollama_{i}",
                    name=fn.get("name", ""),
                    arguments=fn.get("arguments", {})
                ))

            return LLMResponse(
                content=text_content,
                tool_calls=tool_calls,
                finish_reason="stop",
                usage={"total_duration": data.get("total_duration", 0)}
            )
