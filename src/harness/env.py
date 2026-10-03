"""Actionable Sandbox Environment for EnvHarness.

Implements or wraps google-research/envharness ActionableEnv interface
for deterministic agent contract verification.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from src.harness.tools import ContractViolationError, ToolRegistry

logger = logging.getLogger(__name__)

# Attempt to import official google-research/envharness ActionableEnv
try:
    from envharness.environment import ActionableEnv  # type: ignore
except ImportError:
    class ActionableEnv:  # type: ignore
        """Fallback base class mimicking ActionableEnv interface."""
        def reset(self) -> Any:
            raise NotImplementedError
        def step(self, action: Any) -> Tuple[Any, float, bool, Dict[str, Any]]:
            raise NotImplementedError


class ActionableSandboxEnv(ActionableEnv):
    """A sandboxed execution environment that enforces agent contract compliance."""

    def __init__(self, sandbox_root: str) -> None:
        self.sandbox_root = sandbox_root
        self.tool_registry = ToolRegistry(sandbox_root=sandbox_root)
        self.history: List[Dict[str, Any]] = []
        self._step_count: int = 0
        self._max_steps: int = 50

    def reset(self) -> Dict[str, Any]:
        """Reset the environment to its initial state."""
        self.history.clear()
        self._step_count = 0
        return {
            "status": "READY",
            "sandbox_root": self.sandbox_root,
            "available_tools": list(self.tool_registry._tools.keys()),
        }

    def step(self, action: Dict[str, Any]) -> Tuple[Dict[str, Any], float, bool, Dict[str, Any]]:
        """Execute one agent action step and observe outcome.

        Args:
            action: Dictionary with {"tool": "<tool_name>", "args": {<kwargs>}}
                    or {"action_type": "finish", "message": "..."}

        Returns:
            Tuple of (observation, reward, done, info)

        Raises:
            ContractViolationError: If action breaks security or protocol contracts.
        """
        self._step_count += 1
        if self._step_count > self._max_steps:
            return (
                {"error": "Max steps exceeded"},
                0.0,
                True,
                {"reason": "timeout"},
            )

        tool_name = action.get("tool")
        args = action.get("args", {})

        if action.get("action_type") == "finish":
            done = True
            obs = {"output": action.get("message", "Task finished")}
            return obs, 1.0, done, {"reason": "completed"}

        if not tool_name:
            raise ContractViolationError("Contract Violation: Action missing required 'tool' field.")

        # Execute tool via registry with strict containment checks
        try:
            result = self.tool_registry.execute(tool_name, args)
            obs = {"status": "SUCCESS", "result": result}
            reward = 1.0
            done = False
            info = {"tool": tool_name}
        except ContractViolationError:
            # Re-raise contract violations for deterministic test detection
            logger.error(f"Contract violation detected on tool '{tool_name}' with args {args}")
            raise
        except Exception as e:
            obs = {"status": "ERROR", "error": str(e)}
            reward = -0.5
            done = False
            info = {"error": type(e).__name__}

        self.history.append({"action": action, "observation": obs})
        return obs, reward, done, info
