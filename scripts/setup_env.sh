#!/usr/bin/env bash
# ==============================================================================
# Setup Environment for LiteRT-LM & GemmaCore Mac
# Python 3.12 + Apple Silicon Metal Support
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "=== [1/4] Checking Python 3.12 Runtime ==="
PYTHON_BIN=""
if [ -x "/opt/homebrew/bin/python3.12" ]; then
    PYTHON_BIN="/opt/homebrew/bin/python3.12"
elif command -v python3.12 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3.12)"
elif [ -x "/usr/local/bin/python3.12" ]; then
    PYTHON_BIN="/usr/local/bin/python3.12"
else
    echo "Error: Python 3.12 was not found. Please install python@3.12 via Homebrew."
    exit 1
fi

echo "Using Python binary: ${PYTHON_BIN} ($(${PYTHON_BIN} --version))"

VENV_DIR="${PROJECT_ROOT}/litert-env"

echo "=== [2/4] Setting up Virtual Environment: ${VENV_DIR} ==="
if [ ! -d "${VENV_DIR}" ]; then
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
    echo "Virtual environment created."
else
    echo "Virtual environment already exists."
fi

# Activate venv
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

echo "=== [3/4] Upgrading pip and installing dependencies ==="
pip install --upgrade pip

if [ -f "${PROJECT_ROOT}/requirements.txt" ]; then
    echo "Installing from requirements.txt..."
    pip install -r "${PROJECT_ROOT}/requirements.txt"
fi

echo "=== [4/4] Setting up EnvHarness (Google Research) ==="
ENVHARNESS_DIR="${PROJECT_ROOT}/third_party/envharness"
if [ ! -d "${ENVHARNESS_DIR}" ]; then
    mkdir -p "${PROJECT_ROOT}/third_party"
    echo "Cloning google-research/envharness into ${ENVHARNESS_DIR}..."
    if git clone https://github.com/google-research/envharness.git "${ENVHARNESS_DIR}" 2>/dev/null; then
        echo "Installing envharness in editable mode..."
        pip install -e "${ENVHARNESS_DIR}" || echo "Warning: envharness pip install -e had non-critical warnings."
    else
        echo "Notice: Could not clone envharness directly via git (possibly sandboxed or network isolated)."
        echo "A local fallback harness compatible with ActionableEnv interface will be provided in src/harness."
    fi
else
    echo "EnvHarness already present at ${ENVHARNESS_DIR}."
fi

echo "=== Environment Setup Complete! ==="
python -c "import sys; print(f'Active Python: {sys.executable}')"
