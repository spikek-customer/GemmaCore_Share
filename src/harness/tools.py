"""Tool Registry and Execution Contracts for EnvHarness Sandbox.

Enforces deterministic access control, directory containment, and input validation.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


class ContractViolationError(Exception):
    """Raised when an agent violates tool execution contracts."""
    pass


@dataclass
class ToolContract:
    """Security and behavioral contract for a callable tool."""
    name: str
    description: str
    allowed_dirs: List[str] = field(default_factory=list)
    requires_confirmation: bool = False


class ToolRegistry:
    """Registry maintaining active agent tools and validating invocation parameters."""

    def __init__(self, sandbox_root: str) -> None:
        self.sandbox_root = os.path.abspath(sandbox_root)
        os.makedirs(self.sandbox_root, exist_ok=True)
        self._tools: Dict[str, Callable[..., Any]] = {}
        self._contracts: Dict[str, ToolContract] = {}

        self._register_default_tools()

    def register(
        self,
        name: str,
        func: Callable[..., Any],
        contract: ToolContract,
    ) -> None:
        """Register a new tool with strict contract rules."""
        self._tools[name] = func
        self._contracts[name] = contract

    def _register_default_tools(self) -> None:
        """Register built-in safe file and arithmetic tools."""
        # 1. read_file
        self.register(
            name="read_file",
            func=self._tool_read_file,
            contract=ToolContract(
                name="read_file",
                description="Read text contents of a file within the sandbox directory.",
                allowed_dirs=[self.sandbox_root],
            ),
        )

        # 2. write_file
        self.register(
            name="write_file",
            func=self._tool_write_file,
            contract=ToolContract(
                name="write_file",
                description="Write text contents to a file within the sandbox directory.",
                allowed_dirs=[self.sandbox_root],
            ),
        )

        # 3. calculate
        self.register(
            name="calculate",
            func=self._tool_calculate,
            contract=ToolContract(
                name="calculate",
                description="Perform basic mathematical expression calculation.",
            ),
        )

    def execute(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """Execute a tool after verifying its contract."""
        if tool_name not in self._tools:
            raise ContractViolationError(
                f"Contract Violation: Tool '{tool_name}' is not registered in the ToolRegistry."
            )

        contract = self._contracts[tool_name]

        # Verify path containment if tool requires file access
        if "path" in args and contract.allowed_dirs:
            target_path = os.path.abspath(os.path.join(self.sandbox_root, args["path"]))
            is_contained = any(
                target_path == allowed or target_path.startswith(allowed + os.sep)
                for allowed in contract.allowed_dirs
            )
            if not is_contained:
                raise ContractViolationError(
                    f"Contract Violation: Path traversal detected. Target path '{target_path}' "
                    f"is outside allowed sandbox root '{self.sandbox_root}'."
                )
            args["_resolved_path"] = target_path

        return self._tools[tool_name](**args)

    def _tool_read_file(self, path: str, _resolved_path: Optional[str] = None) -> str:
        target = _resolved_path or os.path.abspath(os.path.join(self.sandbox_root, path))
        if not os.path.exists(target):
            raise FileNotFoundError(f"File not found: {path}")
        with open(target, "r", encoding="utf-8") as f:
            return f.read()

    def _tool_write_file(self, path: str, content: str, _resolved_path: Optional[str] = None) -> str:
        target = _resolved_path or os.path.abspath(os.path.join(self.sandbox_root, path))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote {len(content)} characters to {path}"

    def _tool_calculate(self, expression: str) -> str:
        # Safe deterministic evaluation of basic arithmetic
        allowed_chars = set("0123456789+-*/(). ")
        if not set(expression).issubset(allowed_chars):
            raise ContractViolationError(
                f"Contract Violation: Invalid characters in arithmetic expression: {expression}"
            )
        try:
            # Evaluate sanitized arithmetic expression safely
            val = eval(expression, {"__builtins__": {}}, {})  # nosec
            return str(val)
        except Exception as e:
            raise ContractViolationError(f"Calculation error: {e}")
