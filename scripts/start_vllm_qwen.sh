#!/usr/bin/env bash
set -euo pipefail

runtime_root="${WEBPILOT_VLLM_HOME:-/root/autodl-tmp/vllm-qwen}"
model_root="${WEBPILOT_MODEL_HOME:-/root/autodl-tmp/models}"
model="${VLLM_MODEL:-Qwen/Qwen2.5-7B-Instruct}"
api_key="${VLLM_API_KEY:-local-webpilot-only}"
mkdir -p "${model_root}/huggingface"
# FlashInfer invokes `ninja` during its first sampling-kernel build.  vLLM is
# called by absolute path, so expose this dedicated environment's tools too.
export PATH="${runtime_root}/.venv/bin:${PATH}"

export HF_HOME="${model_root}/huggingface"
# The instance cannot reach huggingface.co directly.  HF_ENDPOINT remains
# overrideable so an environment with direct access can use the official host.
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
# The host cannot reach the Hugging Face Xet CAS domain.  Keep weights on the
# reachable HTTP mirror instead of silently falling back to Xet.
export HF_HUB_DISABLE_XET="${HF_HUB_DISABLE_XET:-1}"
exec "${runtime_root}/.venv/bin/vllm" serve "${model}" \
  --host 127.0.0.1 --port "${VLLM_PORT:-8001}" \
  --api-key "${api_key}" \
  --dtype auto --max-model-len "${VLLM_MAX_MODEL_LEN:-8192}" \
  --gpu-memory-utilization "${VLLM_GPU_MEMORY_UTILIZATION:-0.82}" \
  --enable-auto-tool-choice --tool-call-parser hermes
