from __future__ import annotations

import argparse
from pathlib import Path

from webpilot.regression.generator import write_pytest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("trajectory", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--test-name", required=True)
    args = parser.parse_args()
    print(write_pytest(trajectory_path=args.trajectory, output_path=args.out, test_name=args.test_name))


if __name__ == "__main__":
    main()
