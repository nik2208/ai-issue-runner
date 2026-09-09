"""Job management and execution endpoints."""

import asyncio
import uuid
import time
from pathlib import Path
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from ai_runner.types import StructuredPlan, Job
from ai_runner.harnesses.native import NativeHarness
from ai_runner.harnesses.agy import AgyHarness
from ai_runner.harnesses.opencode import OpenCodeHarness
from ai_runner.harnesses.pi import PiHarness
from ai_runner.server.routes.ws import ws_manager

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

# In-memory job repository
JOBS: Dict[str, Job] = {}

def get_harness(harness_type: str, workspace_path: Path):
    if harness_type == "agy":
        return AgyHarness(workspace_path)
    elif harness_type == "opencode":
        return OpenCodeHarness(workspace_path)
    elif harness_type == "pi":
        return PiHarness(workspace_path)
    return NativeHarness(workspace_path)

async def run_job_task(job: Job, workspace_dir: str):
    job.status = "running"
    job.updated_at = time.time()
    workspace_path = Path(workspace_dir).resolve()

    async def on_log(message: str):
        job.logs.append(message)
        await ws_manager.broadcast({
            "type": "log",
            "job_id": job.id,
            "message": message,
            "timestamp": time.time()
        })

    try:
        harness = get_harness(job.plan.harness, workspace_path)
        success = await harness.run_plan(job.plan, on_log=on_log)
        job.status = "completed" if success else "failed"
        job.updated_at = time.time()
        await ws_manager.broadcast({
            "type": "job_status",
            "job_id": job.id,
            "status": job.status
        })
    except Exception as e:
        job.status = "failed"
        job.error = str(e)
        job.updated_at = time.time()
        await on_log(f"💥 Error: {str(e)}")
        await ws_manager.broadcast({
            "type": "job_status",
            "job_id": job.id,
            "status": "failed",
            "error": str(e)
        })

@router.get("", response_model=List[Job])
async def list_jobs():
    return list(JOBS.values())

@router.post("", response_model=Job)
async def create_job(plan: StructuredPlan, background_tasks: BackgroundTasks, workspace_dir: Optional[str] = None):
    job_id = f"job-{uuid.uuid4().hex[:8]}"
    ws = workspace_dir or str(Path.cwd())
    
    job = Job(
        id=job_id,
        plan=plan,
        status="pending",
        created_at=time.time(),
        updated_at=time.time()
    )
    JOBS[job_id] = job
    
    background_tasks.add_task(run_job_task, job, ws)
    return job

@router.get("/{job_id}", response_model=Job)
async def get_job(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    return JOBS[job_id]

@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    job = JOBS[job_id]
    job.status = "cancelled"
    job.updated_at = time.time()
    return {"status": "cancelled", "job_id": job_id}
