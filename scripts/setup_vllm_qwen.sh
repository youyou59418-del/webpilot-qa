#!/usr/bin/env bash
set -euo pipefail

# Keep the inference runtime isolated from webpilot-qa/.venv.
# This profile is validated for the AutoDL RTX 4090 host whose driver exposes
# CUDA 12.6: vLLM 0.8.3 + PyTorch 2.6.0+cu124.
runtime_root="${WEBPILOT_VLLM_HOME:-/root/autodl-tmp/vllm-qwen-cu121}"
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

python_bin="${runtime_root}/.venv/bin/python"
"${python_bin}" -m pip install --upgrade pip setuptools wheel ninja
"${python_bin}" -m pip install "vllm==0.8.3"
# Transformers 5.x changes the Qwen2 tokenizer interface expected by vLLM 0.8.3.
# Pin the validated compatible pair instead of accepting the newest resolver result.
"${python_bin}" -m pip install --upgrade --force-reinstall   "transformers==4.51.3" "numpy==2.1.3"
"${python_bin}" -m pip check
"${python_bin}" - <<'PY'
import torch, vllm
print({"torch": torch.__version__, "cuda": torch.version.cuda,
       "cuda_available": torch.cuda.is_available(), "vllm": vllm.__version__})
assert torch.cuda.is_available(), "CUDA is not visible inside the independent vLLM environment."
PY
