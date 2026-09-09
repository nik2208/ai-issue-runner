"""Core schemas and type definitions for the AI Issue Runner."""

from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field
import time

AcceptanceCriterionType = Literal["command", "file_exists", "regex_match", "custom"]
HarnessType = Literal["native", "agy", "opencode", "pi"]
JobStatus = Literal["pending", "running", "verifying", "completed", "failed", "cancelled"]
AuthMode = Literal["oauth", "api_key", "none"]

class AcceptanceCriterion(BaseModel):
    id: str
    type: AcceptanceCriterionType = "command"
    description: str
    command: Optional[str] = None
    expected_exit_code: int = 0
    path: Optional[str] = None
    pattern: Optional[str] = None
    critical: bool = True
    timeout_seconds: int = 120

class VerificationResult(BaseModel):
    criterion_id: str
    passed: bool
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    message: str = ""
    duration_ms: float = 0.0

class PlanPhase(BaseModel):
    id: str
    title: str
    description: str
    target_files: List[str] = Field(default_factory=list)
    completed: bool = False

class StructuredPlan(BaseModel):
    version: str = "1.0"
    task_id: str
    title: str
    summary: str
    phases: List[PlanPhase] = Field(default_factory=list)
    acceptance_criteria: List[AcceptanceCriterion] = Field(default_factory=list)
    max_iterations: int = 15
    timeout_seconds: int = 1800
    harness: HarnessType = "native"
    provider: Optional[str] = None
    model: Optional[str] = None

class Job(BaseModel):
    id: str
    plan: StructuredPlan
    status: JobStatus = "pending"
    current_iteration: int = 0
    logs: List[str] = Field(default_factory=list)
    verification_history: List[List[VerificationResult]] = Field(default_factory=list)
    error: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

class AuthStatus(BaseModel):
    provider: str
    authenticated: bool
    auth_mode: AuthMode = "none"
    user_email: Optional[str] = None
    expires_at: Optional[float] = None

class RunnerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 4242
    data_dir: str = "~/.ai-runner"
    default_provider: str = "google"
    default_model: str = "gemini-2.5-pro"
    github_webhook_secret: Optional[str] = None

class WebhookPayload(BaseModel):
    action: Optional[str] = None
    issue: Optional[Dict[str, Any]] = None
    repository: Optional[Dict[str, Any]] = None
    comment: Optional[Dict[str, Any]] = None
