"""Contract and Deterministic Verification Tests for EnvHarness.

Covers TEST-006.
Uses standard library unittest.
"""

import os
import shutil
import tempfile
import unittest
from src.harness.runner import EnvHarnessRunner


class TestEnvHarness(unittest.TestCase):

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="envharness_test_")
        self.runner = EnvHarnessRunner(sandbox_root=self.temp_dir)

    def tearDown(self) -> None:
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_harness_safe_actions_pass(self) -> None:
        """TEST-006: Verify authorized agent actions succeed within sandbox."""
        actions = [
            {"tool": "write_file", "args": {"path": "test.txt", "content": "Hello Sandbox"}},
            {"tool": "read_file", "args": {"path": "test.txt"}},
            {"tool": "calculate", "args": {"expression": "100 + 20 * 2"}},
            {"action_type": "finish", "message": "Done"},
        ]
        result = self.runner.run_scenario("Safe Operation", actions, expect_violation=False)
        self.assertTrue(result["passed"])
        self.assertEqual(result["steps_executed"], 4)
        self.assertFalse(result["violation_occurred"])

    def test_harness_path_traversal_violation_caught(self) -> None:
        """TEST-006: Verify unauthorized path traversal outside sandbox triggers ContractViolationError."""
        actions = [
            {"tool": "read_file", "args": {"path": "../../sensitive.key"}}
        ]
        result = self.runner.run_scenario("Path Traversal Attack", actions, expect_violation=True)
        self.assertTrue(result["passed"])  # Passed because violation was correctly caught
        self.assertTrue(result["violation_occurred"])
        self.assertIn("Path traversal detected", result["violation_detail"])

    def test_harness_unregistered_tool_violation_caught(self) -> None:
        """TEST-006: Verify calling non-existent tool triggers ContractViolationError."""
        actions = [
            {"tool": "bash_shell", "args": {"command": "whoami"}}
        ]
        result = self.runner.run_scenario("Unauthorized Tool", actions, expect_violation=True)
        self.assertTrue(result["passed"])
        self.assertTrue(result["violation_occurred"])
        self.assertIn("not registered", result["violation_detail"])


if __name__ == "__main__":
    unittest.main()
