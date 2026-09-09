import pytest
from ai_runner.types import (
    AcceptanceCriterion,
    PlanPhase,
    StructuredPlan,
    Job,
    VerificationResult,
    RunnerConfig,
)

def test_acceptance_criterion_defaults():
    ac = AcceptanceCriterion(
        id="test_1",
        description="Verify pytest passes",
        command="pytest"
    )
    assert ac.id == "test_1"
    assert ac.type == "command"
    assert ac.critical is True
    assert ac.expected_exit_code == 0
    assert ac.timeout_seconds == 120

def test_structured_plan_serialization():
    phase = PlanPhase(id="p1", title="Setup", description="Init database", target_files=["db.py"])
    ac = AcceptanceCriterion(id="ac1", description="Check db file exists", type="file_exists", path="db.py")
    
    plan = StructuredPlan(
        task_id="TASK-101",
        title="Database setup",
        summary="Set up SQLite DB",
        phases=[phase],
        acceptance_criteria=[ac],
        max_iterations=10,
        harness="native"
    )

    data = plan.model_dump()
    assert data["task_id"] == "TASK-101"
    assert len(data["phases"]) == 1
    assert data["phases"][0]["target_files"] == ["db.py"]
    assert len(data["acceptance_criteria"]) == 1

    restored = StructuredPlan(**data)
    assert restored.task_id == plan.task_id
    assert restored.phases[0].id == "p1"
    assert restored.acceptance_criteria[0].path == "db.py"

def test_job_lifecycle():
    plan = StructuredPlan(
        task_id="TASK-1",
        title="Test",
        summary="Test job",
        phases=[],
        acceptance_criteria=[]
    )
    job = Job(id="job-1", plan=plan)
    assert job.status == "pending"
    assert job.current_iteration == 0
    
    res = VerificationResult(
        criterion_id="ac1",
        passed=True,
        exit_code=0,
        stdout="All tests passed"
    )
    job.verification_history.append([res])
    assert len(job.verification_history) == 1
    assert job.verification_history[0][0].passed is True
