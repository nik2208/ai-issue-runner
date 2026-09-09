"""Google Gemini / Code Assist provider driver."""

from typing import List, Optional, Dict, Any
import httpx
from ai_runner.providers.base import BaseProvider, LLMMessage, ToolDefinition, LLMResponse, ToolCall

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

class GoogleProvider(BaseProvider):
    def __init__(self, token_or_key: str, is_oauth: bool = False, default_model: str = "gemini-2.5-pro"):
        super().__init__(default_model=default_model)
        self.token_or_key = token_or_key
        self.is_oauth = is_oauth

    def _convert_messages(self, messages: List[LLMMessage]) -> tuple:
        system_instruction = None
        contents = []

        for msg in messages:
            if msg.role == "system":
                system_instruction = {"parts": [{"text": msg.content}]}
            elif msg.role in ("user", "tool"):
                # Handle tool response
                if msg.role == "tool" and msg.name:
                    contents.append({
                        "role": "user",
                        "parts": [{
                            "functionResponse": {
                                "name": msg.name,
                                "response": {"result": msg.content}
                            }
                        }]
                    })
                else:
                    contents.append({
                        "role": "user",
                        "parts": [{"text": msg.content}]
                    })
            elif msg.role == "assistant":
                parts = []
                if msg.content:
                    parts.append({"text": msg.content})
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        parts.append({
                            "functionCall": {
                                "name": tc.name,
                                "args": tc.arguments
                            }
                        })
                if parts:
                    contents.append({"role": "model", "parts": parts})

        return system_instruction, contents

    async def chat(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[ToolDefinition]] = None,
        model: Optional[str] = None,
        temperature: float = 0.2
    ) -> LLMResponse:
        model_name = model or self.default_model
        if not model_name.startswith("models/"):
            model_name = f"models/{model_name}"

        url = f"{GEMINI_API_BASE}/{model_name}:generateContent"
        headers = {"Content-Type": "application/json"}
        params = {}

        if self.is_oauth:
            headers["Authorization"] = f"Bearer {self.token_or_key}"
        else:
            params["key"] = self.token_or_key

        system_instruction, contents = self._convert_messages(messages)
        body: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature
            }
        }
        if system_instruction:
            body["systemInstruction"] = system_instruction

        if tools:
            func_decls = []
            for t in tools:
                func_decls.append({
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters
                })
            body["tools"] = [{"functionDeclarations": func_decls}]

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers=headers, params=params, json=body)
            if resp.status_code != 200:
                raise RuntimeError(f"Google Gemini error ({resp.status_code}): {resp.text}")

            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return LLMResponse(content="")

            first = candidates[0]
            parts = first.get("content", {}).get("parts", [])
            text_content = ""
            tool_calls = []

            for i, p in enumerate(parts):
                if "text" in p:
                    text_content += p["text"]
                elif "functionCall" in p:
                    fc = p["functionCall"]
                    tool_calls.append(ToolCall(
                        id=f"call_{fc['name']}_{i}",
                        name=fc["name"],
                        arguments=fc.get("args", {})
                    ))

            finish_reason = "tool_calls" if tool_calls else "stop"
            return LLMResponse(
                content=text_content,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
                usage=data.get("usageMetadata", {})
            )
