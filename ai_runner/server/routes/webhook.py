"""GitHub Webhook ingestion endpoint."""

import hmac
import hashlib
import json
import uuid
import time
from pathlib import Path
from typing import Optional, Dict, Any
from fastapi import APIRouter, Request, Header, HTTPException, BackgroundTasks
from ai_runner.config import load_config
from ai_runner.types import StructuredPlan, PlanPhase, AcceptanceCriterion, Job
from ai_runner.server.routes.jobs import JOBS, run_job_task

router = APIRouter(prefix="/api/webhook", tags=["webhook"])

def verify_github_signature(secret: str, payload_bytes: bytes, signature_header: Optional[str]) -> bool:
    if not signature_header:
        return False
    sha_name, signature = signature_header.split("=")
    if sha_name != "sha256":
        return False
    mac = hmac.new(secret.encode("utf-8"), msg=payload_bytes, digestmod=hashlib.sha256)
    return hmac.compare_digest(mac.hexdigest(), signature)

@router.post("/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: Optional[str] = Header(None),
    x_hub_signature_256: Optional[str] = Header(None)
):
    body_bytes = await request.body()
    config = load_config()

    if config.github_webhook_secret:
        if not verify_github_signature(config.github_webhook_secret, body_bytes, x_hub_signature_256):
            raise HTTPException(status_code=401, detail="Invalid GitHub webhook HMAC signature")

    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    action = payload.get("action")
    issue = payload.get("issue")
    comment = payload.get("comment")
    repo = payload.get("repository", {})

    should_trigger = False
    task_title = ""
    task_body = ""
    issue_number = None

    if x_github_event == "issues" and action in ("opened", "labeled"):
        labels = [l.get("name") for l in issue.get("labels", [])]
        if "ai-run" in labels or action == "opened":
            should_trigger = True
            task_title = issue.get("title", "GitHub Issue")
            task_body = issue.get("body", "")
            issue_number = issue.get("number")

    elif x_github_event == "issue_comment" and action == "created":
        comment_body = comment.get("body", "")
        if "@ai-runner" in comment_body or "/fix" in comment_body or "/solve" in comment_body:
            should_trigger = True
            task_title = f"Fix for Issue #{issue.get('number')}: {issue.get('title')}"
            task_body = f"Issue Description:\n{issue.get('body')}\n\nUser Instruction:\n{comment_body}"
            issue_number = issue.get("number")

    if not should_trigger:
        return {"status": "ignored", "reason": "No triggering action/label found"}

    # Automatically construct a structured plan
    task_id = f"GH-{issue_number or uuid.uuid4().hex[:6]}"
    plan = StructuredPlan(
        task_id=task_id,
        title=task_title,
        summary=task_body,
        phases=[
            PlanPhase(id="phase-1", title="Investigate & Implement", description=task_body)
        ],
        acceptance_criteria=[
            AcceptanceCriterion(
                id="tests_pass",
                description="Project automated tests must pass",
                command="pytest || npm test || cargo test",
                expected_exit_code=0
            )
        ],
        harness="native"
    )

    job_id = f"job-{uuid.uuid4().hex[:8]}"
    job = Job(
        id=job_id,
        plan=plan,
        status="pending",
        created_at=time.time(),
        updated_at=time.time()
    )
    JOBS[job_id] = job
    
    background_tasks.add_task(run_job_task, job, str(Path.cwd()))
    return {"status": "enqueued", "job_id": job_id, "task_id": task_id}
