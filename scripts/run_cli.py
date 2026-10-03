#!/usr/bin/env python3
"""CLI No-Code Inference Wrapper for LiteRT-LM & GemmaCore Mac.

Allows quick model testing, downloading from Hugging Face, or local model execution
conforming to official LiteRT-LM CLI specifications.
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
from typing import List, Optional

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("run_cli")


def build_litert_lm_command(
    prompt: str,
    backend: str = "gpu",
    model_path: Optional[str] = None,
    huggingface_repo: Optional[str] = None,
    extra_flags: Optional[List[str]] = None,
) -> List[str]:
    """Construct command arguments for litert-lm run."""
    valid_backends = {"gpu", "cpu", "npu"}
    if backend.lower() not in valid_backends:
        raise ValueError(
            f"Invalid backend '{backend}'. Must be one of: {', '.join(sorted(valid_backends))}"
        )

    cmd = ["litert-lm", "run"]

    if huggingface_repo:
        cmd.append(f"--from-huggingface-repo={huggingface_repo}")
    elif model_path:
        cmd.append(f"--model_path={model_path}")
    else:
        raise ValueError("Either --model_path or --from-huggingface-repo must be specified.")

    cmd.append(f"--backend={backend.lower()}")
    cmd.append(f"--prompt={prompt}")

    if extra_flags:
        cmd.extend(extra_flags)

    return cmd


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run LiteRT-LM models via CLI on macOS Apple Silicon."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--from-huggingface-repo",
        type=str,
        help="Hugging Face model repository ID (e.g. google/gemma-4-12b-it)",
    )
    group.add_argument(
        "--model-path",
        type=str,
        help="Path to local .litertlm model weight file",
    )
    parser.add_argument(
        "--backend",
        type=str,
        default="gpu",
        choices=["gpu", "cpu", "npu"],
        help="Inference backend (default: gpu / Apple Metal)",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        required=True,
        help="Input text prompt",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print assembled command without executing",
    )

    args, unknown = parser.parse_known_args()

    try:
        cmd = build_litert_lm_command(
            prompt=args.prompt,
            backend=args.backend,
            model_path=args.model_path,
            huggingface_repo=args.from_huggingface_repo,
            extra_flags=unknown,
        )
    except ValueError as e:
        logger.error(str(e))
        sys.exit(2)

    logger.info(f"Assembled Command: {' '.join(cmd)}")

    if args.dry_run:
        logger.info("[Dry Run] Command validation succeeded.")
        sys.exit(0)

    # Check if litert-lm is installed in PATH
    if not shutil.which("litert-lm"):
        logger.warning(
            "'litert-lm' CLI tool not found in current PATH. "
            "Please activate your virtual environment (source litert-env/bin/activate) "
            "or install it via: pip install litert-lm"
        )
        sys.exit(127)

    try:
        result = subprocess.run(cmd, check=True)
        sys.exit(result.returncode)
    except subprocess.CalledProcessError as e:
        logger.error(f"Execution failed with return code {e.returncode}")
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        logger.info("\nExecution cancelled by user.")
        sys.exit(130)


if __name__ == "__main__":
    main()
