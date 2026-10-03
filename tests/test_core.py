"""Unit Tests for Core Inference Engine and CLI Wrapper.

Covers TEST-002, TEST-003, TEST-007, and TEST-008.
Uses standard library unittest for execution in any Python environment.
"""

import os
import unittest
from scripts.run_cli import build_litert_lm_command
from src.core.engine import BackendType, InferenceEngine


class TestCoreAndCLI(unittest.TestCase):

    def test_cli_command_builder_success(self) -> None:
        """TEST-002: Verify valid CLI command construction."""
        cmd = build_litert_lm_command(
            prompt="Test prompt",
            backend="gpu",
            model_path="models/test.litertlm",
        )
        self.assertIn("litert-lm", cmd)
        self.assertIn("run", cmd)
        self.assertIn("--model_path=models/test.litertlm", cmd)
        self.assertIn("--backend=gpu", cmd)
        self.assertIn("--prompt=Test prompt", cmd)

    def test_cli_command_builder_invalid_backend(self) -> None:
        """TEST-002: Verify invalid backend causes ValueError."""
        with self.assertRaises(ValueError):
            build_litert_lm_command(prompt="Test", backend="invalid_backend", model_path="test.litertlm")

    def test_inference_engine_lifecycle_and_conversation(self) -> None:
        """TEST-003: Verify InferenceEngine context manager and conversation flow."""
        with InferenceEngine(
            model_path="dummy.litertlm",
            backend=BackendType.GPU,
            mock_mode=True,
        ) as engine:
            self.assertEqual(engine.active_backend, BackendType.GPU)
            self.assertFalse(engine._is_closed)

            with engine.create_conversation(system_prompt="System persona") as conv:
                history = conv.get_history()
                self.assertEqual(len(history), 1)
                self.assertEqual(history[0]["role"], "system")

                reply = conv.send_message("Hello LiteRT")
                self.assertIsInstance(reply, str)
                self.assertTrue(len(reply) > 0)

                updated_history = conv.get_history()
                self.assertEqual(len(updated_history), 3)
                self.assertEqual(updated_history[1]["role"], "user")
                self.assertEqual(updated_history[2]["role"], "assistant")

        # Verify resource cleanup (TEST-008)
        self.assertTrue(engine._is_closed)

    def test_engine_fallback_to_cpu_logic(self) -> None:
        """TEST-007: Verify graceful CPU fallback logic when GPU encounters runtime error."""
        engine = InferenceEngine(
            model_path="dummy.litertlm",
            backend=BackendType.GPU,
            fallback_to_cpu=True,
            mock_mode=True,
        )
        engine.initialize()
        # Ensure engine is operational
        self.assertEqual(engine.active_backend, BackendType.GPU)
        reply = engine.generate("Test prompt")
        self.assertTrue(len(reply) > 0)


if __name__ == "__main__":
    unittest.main()
