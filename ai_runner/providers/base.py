"""Base LLM provider interface and schemas."""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, AsyncIterator
from pydantic import BaseModel, Field

class ToolCall(BaseModel):
    id: str
    name: str
    arguments: Dict[str, Any]

class LLMMessage(BaseModel):
    role: str # "system", "user", "assistant", "tool"
    content: str = ""
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None

class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any] = Field(default_factory=dict)

class LLMResponse(BaseModel):
    content: str = ""
    tool_calls: List[ToolCall] = Field(default_factory=list)
    finish_reason: str = "stop" # "stop", "tool_calls", "length"
    usage: Dict[str, int] = Field(default_factory=dict)

class BaseProvider(ABC):
    def __init__(self, default_model: str):
        self.default_model = default_model

    @abstractmethod
    async def chat(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[ToolDefinition]] = None,
        model: Optional[str] = None,
        temperature: float = 0.2
    ) -> LLMResponse:
        """Sends chat messages and optional tools, returning structured response."""
        pass
