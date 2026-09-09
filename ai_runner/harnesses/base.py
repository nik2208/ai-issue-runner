"""Abstract base class for agent harnesses."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Optional, Awaitable
from ai_runner.types import StructuredPlan, Job

LogCallback = Callable[[str], Awaitable[None]]

class AgentHarness(ABC):
    def __init__(self, workspace_path: str | Path):
        self.workspace_path = Path(workspace_path).resolve()

    @abstractmethod
    async def run_plan(
        self,
        plan: StructuredPlan,
        on_log: Optional[LogCallback] = None
    ) -> bool:
        """Executes a structured plan in a guarded agentic loop until acceptance criteria pass."""
        pass
