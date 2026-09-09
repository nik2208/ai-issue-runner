"""LoopGuard: Guarded agentic loop controller and exit condition enforcer."""

from pathlib import Path
from typing import Tuple, List, Optional
from ai_runner.types import StructuredPlan, VerificationResult
from ai_runner.engine.verifier import AcceptanceVerifier

class LoopGuard:
    def __init__(self, plan: StructuredPlan, workspace_path: str | Path):
        self.plan = plan
        self.workspace_path = Path(workspace_path).resolve()
        self.verifier = AcceptanceVerifier(self.workspace_path)
        self.iteration = 0
        self.max_iterations = plan.max_iterations
        self.verification_history: List[List[VerificationResult]] = []

    async def evaluate_exit(self, agent_summary: str = "") -> Tuple[bool, str, List[VerificationResult]]:
        """Evaluates whether the agent is allowed to terminate.
        
        Returns:
            (can_exit, feedback_message, verification_results)
        """
        self.iteration += 1
        results = await self.verifier.verify_all(self.plan.acceptance_criteria)
        self.verification_history.append(results)

        failed_critical = [
            r for r, c in zip(results, self.plan.acceptance_criteria)
            if not r.passed and c.critical
        ]

        if not failed_critical:
            summary = (
                f"✅ ALL ACCEPTANCE CRITERIA VERIFIED SUCCESSFULLY (Iteration {self.iteration}/{self.max_iterations}).\n"
                f"Completed: {len(results)}/{len(results)} criteria passed."
            )
            return True, summary, results

        # If iteration limit reached, loop terminates with failure
        if self.iteration >= self.max_iterations:
            summary = (
                f"🛑 LOOP TERMINATED: Maximum iterations reached ({self.max_iterations}) "
                f"with {len(failed_critical)} unmet critical criteria."
            )
            return True, summary, results

        # Format diagnostic feedback prompt to force agent self-correction
        feedback_lines = [
            f"❌ COMPLETION REJECTED! (Iteration {self.iteration}/{self.max_iterations})",
            "The following Acceptance Criteria are NOT satisfied and must be fixed:",
            ""
        ]

        for r, c in zip(results, self.plan.acceptance_criteria):
            status_icon = "✅" if r.passed else "❌"
            feedback_lines.append(f"{status_icon} [{c.id}] {c.description}")
            if not r.passed:
                if c.command:
                    feedback_lines.append(f"   Command: `{c.command}` (Exit Code {r.exit_code}, expected {c.expected_exit_code})")
                if r.stderr:
                    trimmed_stderr = r.stderr[-1500:] if len(r.stderr) > 1500 else r.stderr
                    feedback_lines.append(f"   Stderr:\n```\n{trimmed_stderr.strip()}\n```")
                elif r.stdout:
                    trimmed_stdout = r.stdout[-1500:] if len(r.stdout) > 1500 else r.stdout
                    feedback_lines.append(f"   Output:\n```\n{trimmed_stdout.strip()}\n```")
                if r.message:
                    feedback_lines.append(f"   Detail: {r.message}")
            feedback_lines.append("")

        feedback_lines.append(
            "You MUST inspect these failures, modify the relevant files or tests, and run verification again. "
            "Do NOT attempt to finish until all criteria pass."
        )

        return False, "\n".join(feedback_lines), results
