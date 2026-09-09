import pytest
from pathlib import Path
from ai_runner.types import AcceptanceCriterion, StructuredPlan
from ai_runner.engine.verifier import AcceptanceVerifier
from ai_runner.engine.guard import LoopGuard

@pytest.mark.asyncio
async def test_acceptance_verifier_command(tmp_path):
    verifier = AcceptanceVerifier(tmp_path)
    
    # Passing command
    ac_pass = AcceptanceCriterion(
        id="pass_1",
        description="Check echo",
        command="python3 -c 'print(\"hello\"); exit(0)'",
        expected_exit_code=0
    )
    res_pass = await verifier.verify_command(ac_pass)
    assert res_pass.passed is True
    assert res_pass.exit_code == 0
    assert "hello" in res_pass.stdout

    # Failing command
    ac_fail = AcceptanceCriterion(
        id="fail_1",
        description="Failing test",
        command="python3 -c 'import sys; sys.stderr.write(\"Assertion Error\"); exit(1)'",
        expected_exit_code=0
    )
    res_fail = await verifier.verify_command(ac_fail)
    assert res_fail.passed is False
    assert res_fail.exit_code == 1
    assert "Assertion Error" in res_fail.stderr

@pytest.mark.asyncio
async def test_acceptance_verifier_file_and_regex(tmp_path):
    verifier = AcceptanceVerifier(tmp_path)

    # File does not exist initially
    ac_file = AcceptanceCriterion(
        id="file_check",
        description="File exists",
        type="file_exists",
        path="output.txt"
    )
    res = await verifier.verify_file_exists(ac_file)
    assert res.passed is False

    # Create file
    (tmp_path / "output.txt").write_text("API_VERSION = 'v2.4'", encoding="utf-8")
    res2 = await verifier.verify_file_exists(ac_file)
    assert res2.passed is True

    # Regex match
    ac_regex = AcceptanceCriterion(
        id="regex_check",
        description="Version check",
        type="regex_match",
        path="output.txt",
        pattern=r"API_VERSION\s*=\s*'v2\.\d+'"
    )
    res3 = await verifier.verify_regex_match(ac_regex)
    assert res3.passed is True

@pytest.mark.asyncio
async def test_loop_guard_rejection_and_feedback(tmp_path):
    plan = StructuredPlan(
        task_id="T1",
        title="Loop guard test",
        summary="Test",
        acceptance_criteria=[
            AcceptanceCriterion(
                id="cmd_check",
                description="Must exit 0",
                command="python3 -c 'exit(1)'",
                expected_exit_code=0,
                critical=True
            )
        ],
        max_iterations=3
    )

    guard = LoopGuard(plan=plan, workspace_path=tmp_path)
    
    # Iteration 1: Attempt to exit -> Should be rejected
    can_exit, feedback, results = await guard.evaluate_exit("I am finished!")
    assert can_exit is False
    assert "COMPLETION REJECTED" in feedback
    assert "cmd_check" in feedback
    assert guard.iteration == 1

    # Iteration 2: Fix the issue
    plan.acceptance_criteria[0].command = "python3 -c 'exit(0)'"
    can_exit, feedback, results = await guard.evaluate_exit("Fixed it!")
    assert can_exit is True
    assert "ALL ACCEPTANCE CRITERIA VERIFIED SUCCESSFULLY" in feedback
