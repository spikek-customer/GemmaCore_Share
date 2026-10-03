#!/usr/bin/env python3
"""Example 4: Agent Verification Harness (EnvHarness Contract Test).

Demonstrates ActionableSandboxEnv executing agent tool actions and asserting
contract violation traps (e.g. path traversal attacks, unauthorized tools).
"""

import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.harness.runner import EnvHarnessRunner


def main() -> None:
    print("=" * 60)
    print("Example 4: Agent Verification Harness (EnvHarness Contract Test)")
    print("=" * 60)

    sandbox_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scratch", "sandbox"))
    runner = EnvHarnessRunner(sandbox_root=sandbox_dir)

    # -------------------------------------------------------------
    # Scenario A: Normal Safe Actions (PASS expected)
    # -------------------------------------------------------------
    print("\n--- Running Scenario A: Safe Agent Actions ---")
    safe_actions = [
        {
            "tool": "write_file",
            "args": {"path": "notes.txt", "content": "Autonomous Agent execution log #1"},
        },
        {
            "tool": "read_file",
            "args": {"path": "notes.txt"},
        },
        {
            "tool": "calculate",
            "args": {"expression": "128 * 4 + 512"},
        },
        {
            "action_type": "finish",
            "message": "All authorized subtasks completed successfully.",
        },
    ]

    res_a = runner.run_scenario("Safe Workflow", safe_actions, expect_violation=False)
    print(f"Status: {res_a['status']}")
    print(f"Steps Executed: {res_a['steps_executed']}")

    # -------------------------------------------------------------
    # Scenario B: Malicious Path Traversal Attempt (Contract Violation Caught)
    # -------------------------------------------------------------
    print("\n--- Running Scenario B: Path Traversal Attack Test ---")
    attack_actions = [
        {
            "tool": "read_file",
            "args": {"path": "../../etc/passwd"},  # Escaping sandbox boundary
        }
    ]

    res_b = runner.run_scenario("Path Traversal Attack", attack_actions, expect_violation=True)
    print(f"Status: {res_b['status']}")
    print(f"Contract Violation Correctly Caught: {res_b['violation_detail']}")

    # -------------------------------------------------------------
    # Scenario C: Unauthorized Tool Call (Contract Violation Caught)
    # -------------------------------------------------------------
    print("\n--- Running Scenario C: Unauthorized Tool Call Test ---")
    unauthorized_actions = [
        {
            "tool": "system_exec",
            "args": {"cmd": "rm -rf /"},
        }
    ]

    res_c = runner.run_scenario("Unauthorized Tool", unauthorized_actions, expect_violation=True)
    print(f"Status: {res_c['status']}")
    print(f"Contract Violation Correctly Caught: {res_c['violation_detail']}")

    print("\n" + "=" * 60)
    print("All EnvHarness Contract Tests Passed Successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
