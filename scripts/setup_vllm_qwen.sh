#!/usr/bin/env bash
set -euo pipefail

# Deliberately separate from webpilot-qa/.venv.
runtime_root="${WEBPILOT_VLLM_HOME:-/root/autodl-tmp/vllm-qwen}"
bootstrap_python="${VLLM_BOOTSTRAP_PYTHON:-/root/miniconda3/bin/python}"

if [[ ! -x "${bootstrap_python}" ]]; then
  echo "No bootstrap Python at ${bootstrap_python}; set VLLM_BOOTSTRAP_PYTHON." >&2
  exit 1
fi
"${bootstrap_python}" -c 'import sys; assert sys.version_info[:2] == (3, 12), sys.version'

if [[ ! -x "${runtime_root}/.venv/bin/python" ]]; then
  mkdir -p "${runtime_root}"
  "${bootstrap_python}" -m venv "${runtime_root}/.venv"
fi

"${runtime_root}/.venv/bin/python" -m pip install --upgrade pip
# Keep the whole vLLM/Torch family on one resolver-selected CUDA build.
# Do not add a second PyTorch wheel index here: mixed torch/torchaudio builds
# fail at vLLM import time.
# FlashInfer may JIT-compile a sampling kernel on first startup; its `ninja`
# executable must be present even though vLLM itself is otherwise installed.
"${runtime_root}/.venv/bin/python" -m pip install vllm ninja
"${runtime_root}/.venv/bin/python" - <<'PY'
import torch, vllm
print({"torch": torch.__version__, "cuda": torch.version.cuda, "cuda_available": torch.cuda.is_available(), "vllm": vllm.__version__})
assert torch.cuda.is_available(), "CUDA is not visible inside the independent vLLM environment."
PY
