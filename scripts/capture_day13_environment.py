from __future__ import annotations

import argparse
import json
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path


def _version(package: str) -> str | None:
    try:
        module = __import__(package)
    except ImportError:
        return None
    value = getattr(module, "__version__", None)
    return str(value) if value is not None else None


def _nvidia_smi() -> list[dict[str, str]]:
    command = [
        "nvidia-smi",
        "--query-gpu=name,driver_version,memory.total",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        return [{"error": f"{type(exc).__name__}: {exc}"}]
    rows = []
    for line in result.stdout.splitlines():
        name, driver, memory = (item.strip() for item in line.split(",", maxsplit=2))
        rows.append({"name": name, "driver_version": driver, "memory_total_mib": memory})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model", default="Qwen/Qwen2.5-7B-Instruct")
    parser.add_argument("--max-model-len", type=int, default=8192)
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.82)
    args = parser.parse_args()

    torch_version = _version("torch")
    torch_cuda = None
    try:
        import torch

        torch_cuda = torch.version.cuda
    except ImportError:
        pass
    payload = {
        "captured_at": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "model": args.model,
        "max_model_len": args.max_model_len,
        "gpu_memory_utilization": args.gpu_memory_utilization,
        "vllm": _version("vllm"),
        "torch": torch_version,
        "torch_cuda": torch_cuda,
        "torchaudio": _version("torchaudio"),
        "gpus": _nvidia_smi(),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.out)


if __name__ == "__main__":
    main()
