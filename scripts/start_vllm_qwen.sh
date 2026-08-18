#!/usr/bin/env bash
set -euo pipefail

# Validated AutoDL CUDA 12.6 profile. Override these variables when deploying
# elsewhere; do not use webpilot-qa/.venv as the vLLM runtime.
runtime_root="${WEBPILOT_VLLM_HOME:-/root/autodl-tmp/vllm-qwen-cu121}"
model_root="${WEBPILOT_MODEL_HOME:-/root/autodl-tmp/models}"
model="${VLLM_MODEL:-${model_root}/Qwen2.5-14B-Instruct-GPTQ-Int4}"
served_model_name="${VLLM_SERVED_MODEL_NAME:-Qwen2.5-14B-Instruct-GPTQ-Int4}"
api_key="${VLLM_API_KEY:-local-webpilot-only}"

if [[ ! -x "${runtime_root}/.venv/bin/vllm" ]]; then
  echo "No compatible vLLM runtime at ${runtime_root}; run scripts/setup_vllm_qwen.sh first." >&2
  exit 1
fi
if [[ ! -e "${model}" && "${model}" == /* ]]; then
  echo "No local model at ${model}; set VLLM_MODEL to a valid local path or model identifier." >&2
  exit 1
fi

mkdir -p "${model_root}/huggingface"
export PATH="${runtime_root}/.venv/bin:${PATH}"
export HF_HOME="${model_root}/huggingface"
# Keep an override for hosts that can reach the official Hugging Face endpoint.
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
export HF_HUB_DISABLE_XET="${HF_HUB_DISABLE_XET:-1}"

exec "${runtime_root}/.venv/bin/vllm" serve "${model}"   --host 127.0.0.1 --port "${VLLM_PORT:-8001}"   --api-key "${api_key}"   --served-model-name "${served_model_name}"   --dtype auto --max-model-len "${VLLM_MAX_MODEL_LEN:-8192}"   --gpu-memory-utilization "${VLLM_GPU_MEMORY_UTILIZATION:-0.82}"   --enable-auto-tool-choice --tool-call-parser hermes
