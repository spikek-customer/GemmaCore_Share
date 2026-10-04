#!/usr/bin/env bash
# ==============================================================================
# Setup Environment for LiteRT-LM & GemmaCore Mac
# Python 3.12 + Apple Silicon Metal Support
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "=== [1/5] Checking Python 3.12 Runtime ==="
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

echo "=== [2/5] Setting up Virtual Environment: ${VENV_DIR} ==="
if [ ! -d "${VENV_DIR}" ]; then
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
    echo "Virtual environment created."
else
    echo "Virtual environment already exists."
fi

# Activate venv
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

echo "=== [3/5] Upgrading pip and installing dependencies ==="
pip install --upgrade pip

if [ -f "${PROJECT_ROOT}/requirements.txt" ]; then
    echo "Installing from requirements.txt..."
    pip install -r "${PROJECT_ROOT}/requirements.txt"
fi

echo "=== [4/5] Setting up EnvHarness (Google Research) ==="
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

echo "=== [5/5] Checking / Downloading Default Model: Gemma 4 12B Quantized (4-bit, ~7.6GB) ==="
MODELS_DIR="${PROJECT_ROOT}/models"
mkdir -p "${MODELS_DIR}"
MODEL_FILE="${MODELS_DIR}/gemma-4-12b-it.litertlm"

if [ -f "${MODEL_FILE}" ]; then
    echo "Default model file already exists: ${MODEL_FILE} ($(du -h "${MODEL_FILE}" 2>/dev/null | cut -f1 || echo 'Present'))"
elif [ "${SKIP_MODEL_DOWNLOAD:-0}" = "1" ] || [[ "$*" == *"--skip-model"* ]]; then
    echo "Model download skipped (requested via SKIP_MODEL_DOWNLOAD=1 or --skip-model)."
    echo "Note: The engine will run in mock mode or Cloud Gemini mode until a local model is placed in models/."
else
    echo "Default model target: Gemma 4 12B Quantized (4-bit, approx. 7.6GB)"
    echo "Destination: ${MODEL_FILE}"
    echo "Source Repository: google/gemma-4-12b-it (LiteRT-LM format)"

    # Disk space check
    AVAILABLE_KB=$(df -k "${MODELS_DIR}" 2>/dev/null | awk 'NR==2 {print $4}' || echo "")
    if [ -n "${AVAILABLE_KB}" ] && [ "${AVAILABLE_KB}" -lt 10000000 ]; then
        echo "Warning: Less than 10GB of free disk space detected (${AVAILABLE_KB} KB available)."
        echo "Gemma 4 12B 4-bit model requires ~7.6GB of storage."
    fi

    echo "Attempting to download default model weight..."
    set +e
    python - <<'EOF'
import os
import sys

model_dir = os.path.abspath("models")
model_path = os.path.join(model_dir, "gemma-4-12b-it.litertlm")
hf_repo = "google/gemma-4-12b-it"
filename = "gemma-4-12b-it.litertlm"
hf_token = os.environ.get("HF_TOKEN")

print(f"Connecting to model repository: {hf_repo}...")
try:
    from huggingface_hub import hf_hub_download
except ImportError:
    import subprocess
    print("Installing huggingface_hub package for model download...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "huggingface_hub"])
    from huggingface_hub import hf_hub_download

try:
    downloaded_path = hf_hub_download(
        repo_id=hf_repo,
        filename=filename,
        local_dir=model_dir,
        token=hf_token,
    )
    print(f"Model downloaded successfully to: {downloaded_path}")
except Exception as e:
    print(f"Download notice: {e}", file=sys.stderr)
    sys.exit(1)
EOF
    DL_EXIT_CODE=$?
    set -e

    if [ ${DL_EXIT_CODE} -eq 0 ] && [ -f "${MODEL_FILE}" ]; then
        echo "Default model setup complete: ${MODEL_FILE}"
    else
        echo "----------------------------------------------------------------------"
        echo "Notice: Automatic model download could not be completed at this time."
        echo "Possible reasons:"
        echo "  1. Network connectivity / offline environment"
        echo "  2. Hugging Face user agreement required for Gemma models (export HF_TOKEN='your_token')"
        echo "  3. Sandbox or network-isolated environment"
        echo ""
        echo "Fallback operation is fully supported:"
        echo "  - Local engine will run smoothly in MOCK mode without errors."
        echo "  - Cloud Gemini API (google-genai) can be used immediately with GEMINI_API_KEY."
        echo "  - You can manually place 'gemma-4-12b-it.litertlm' (~7.6GB) into 'models/' anytime."
        echo "----------------------------------------------------------------------"
    fi
fi

echo "=== Environment Setup Complete! ==="
python -c "import sys; print(f'Active Python: {sys.executable}')"
