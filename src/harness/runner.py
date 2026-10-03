"""Scenario Runner and Contract Verifier for EnvHarness.

Executes predefined sequence of agent tool calls and asserts contract adherence.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from src.harness.env import ActionableSandboxEnv
from src.harness.tools import ContractViolationError

logger = logging.getLogger(__name__)


class EnvHarnessRunner:
    """Runs deterministic agent scenarios and validates contract compliance."""

    def __init__(self, sandbox_root: str) -> None:
        self.env = ActionableSandboxEnv(sandbox_root=sandbox_root)

    def run_scenario(
        self,
        scenario_name: str,
        actions: List[Dict[str, Any]],
        expect_violation: bool = False,
    ) -> Dict[str, Any]:
        """Execute a series of actions in the environment.

        Args:
            scenario_name: Human readable title of the test scenario.
            actions: List of step actions to execute.
            expect_violation: If True, asserts that a ContractViolationError occurs.

        Returns:
            Dictionary summary with status (PASSED/FAILED) and execution logs.
        """
        self.env.reset()
        execution_trace: List[Dict[str, Any]] = []
        violation_occurred = False
        violation_detail: str = ""

        logger.info(f"Starting scenario: {scenario_name} (actions={len(actions)})")

        for step_idx, action in enumerate(actions):
            try:
                obs, reward, done, info = self.env.step(action)
                execution_trace.append({
                    "step": step_idx,
                    "action": action,
                    "observation": obs,
                    "reward": reward,
                    "done": done,
                })
                if done:
                    break
            except ContractViolationError as e:
                violation_occurred = True
                violation_detail = str(e)
                execution_trace.append({
                    "step": step_idx,
                    "action": action,
                    "contract_violation": violation_detail,
                })
                break

        if expect_violation:
            passed = violation_occurred
            status = "PASSED (Violation Correctly Caught)" if passed else "FAILED (Expected Violation Did Not Occur)"
        else:
            passed = not violation_occurred
            status = "PASSED" if passed else f"FAILED (Unexpected Violation: {violation_detail})"

        return {
            "scenario": scenario_name,
            "passed": passed,
            "status": status,
            "violation_occurred": violation_occurred,
            "violation_detail": violation_detail,
            "steps_executed": len(execution_trace),
            "trace": execution_trace,
        }
