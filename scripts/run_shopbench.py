"""Start the controlled Day 10 ShopBench station."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn

# The script is intentionally runnable without relying on an editable install.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shopbench.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8080, type=int)
    args = parser.parse_args()
    uvicorn.run(create_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
