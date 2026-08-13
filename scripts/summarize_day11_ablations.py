from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aggregate comparable Day 11 live-model reports."
    )
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    reports = sorted(args.input_root.glob("*/report.json"))
    if not reports:
        raise SystemExit(f"No report.json files below {args.input_root}")

    rows: list[dict[str, object]] = []
    for report_path in reports:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        outcomes = report.get("outcomes", [])
        if report.get("execution_mode") != "live_model":
            raise SystemExit(f"Not a live-model report: {report_path}")
        if not isinstance(outcomes, list):
            raise SystemExit(f"Invalid outcomes in {report_path}")
        passed = sum(item.get("status") == "passed" for item in outcomes)
        blocked = sum(item.get("status") == "blocked_by_safety" for item in outcomes)
        failed = sum(item.get("status") == "failed" for item in outcomes)
        attempted = passed + blocked + failed
        rows.append(
            {
                "variant": report.get("variant", report_path.parent.name),
                "model": report.get("model_name", "unknown"),
                "attempted": attempted,
                "passed": passed,
                "blocked_by_safety": blocked,
                "failed": failed,
                "success_rate": 0 if attempted == 0 else passed / attempted,
                "report": str(report_path),
            }
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / "ablation.csv"
    columns = [
        "variant",
        "model",
        "attempted",
        "passed",
        "blocked_by_safety",
        "failed",
        "success_rate",
        "report",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    json_path = args.output_dir / "ablation.json"
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path = args.output_dir / "ablation.md"
    markdown_path.write_text(
        "# Day 11 ablation comparison\n\n"
        "| Variant | Attempted | Passed | Safety blocked | Failed | Success rate |\n"
        "| --- | ---: | ---: | ---: | ---: | ---: |\n"
        + "".join(
            "| {variant} | {attempted} | {passed} | {blocked_by_safety} | {failed} | {success_rate:.1%} |\n".format(
                **row
            )
            for row in rows
        )
        + "\nOnly compare rows with the same task IDs, model, budgets and retry policy.\n",
        encoding="utf-8",
    )
    max_attempted = max(int(row["attempted"]) for row in rows) or 1
    svg_rows = []
    for index, row in enumerate(rows):
        y = 54 + index * 38
        width = 360 * int(row["passed"]) / max_attempted
        svg_rows.append(
            f'<text x="16" y="{y + 16}" font-size="13">{row["variant"]}: {row["passed"]}/{row["attempted"]}</text>'
            f'<rect x="190" y="{y}" width="{width:.1f}" height="22" fill="#16803c"/>'
        )
    chart_path = args.output_dir / "ablation.svg"
    chart_path.write_text(
        "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"620\" "
        f"height=\"{80 + len(rows) * 38}\" viewBox=\"0 0 620 {80 + len(rows) * 38}\">"
        "<rect width=\"100%\" height=\"100%\" fill=\"white\"/>"
        "<text x=\"16\" y=\"28\" font-size=\"18\" font-weight=\"bold\">Day 11 ablation gate</text>"
        + "".join(svg_rows)
        + "</svg>\n",
        encoding="utf-8",
    )
    for path in (json_path, csv_path, markdown_path, chart_path):
        print(path)


if __name__ == "__main__":
    main()
