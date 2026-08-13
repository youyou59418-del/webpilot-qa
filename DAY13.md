# Day 13 - vLLM + Qwen

The local model uses a fresh Python 3.12 environment under `/root/autodl-tmp/vllm-qwen`, not `webpilot-qa/.venv`. Qwen2.5-7B-Instruct is served only on `127.0.0.1:8001` with an OpenAI-compatible API, 8K context, 82% GPU-memory cap, and the vLLM `hermes` tool-call parser. The script installs one resolver-selected CUDA family and then records the actual Torch/CUDA version; do not claim a CUDA version based solely on the host-image label. The current instance cannot reach `huggingface.co` or its Xet CAS host directly, so the launcher defaults to `https://hf-mirror.com` and disables Xet downloads; set `HF_ENDPOINT=https://huggingface.co` and `HF_HUB_DISABLE_XET=0` on an environment with direct access.

```bash
./scripts/setup_vllm_qwen.sh
./scripts/start_vllm_qwen.sh > artifacts/vllm/server.log 2>&1 &
./.venv/bin/python scripts/check_vllm_qwen.py
/root/autodl-tmp/vllm-qwen/.venv/bin/python scripts/capture_day13_environment.py \
  --out artifacts/vllm/environment.json
set -a; source config/model_profiles/qwen2.5-7b-local.env; set +a
```

Then run the same Day 11 task IDs, retry budget, and context limit against the external API baseline and this local model. API compatibility does not establish comparable agent performance; only the archived live ShopBench reports do.

The first verified instance used vLLM 0.27.1, PyTorch 2.13.0+cu130 and TorchAudio 2.11.0+cu130 on an RTX 4090. This is the resolver-selected runtime, not a claim that the host image itself is CUDA 13.0.
