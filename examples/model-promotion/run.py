"""Evaluate a tiny text classifier and gate its real exports against a reference run."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

from evidence_gate.producers import output_sha256, write_report_atomic

FIXTURE = Path(__file__).resolve().parent
MESSAGES = (
    ("There is an outage in our region", "urgent"),
    ("The payment failed and I cannot continue", "urgent"),
    ("We detected a security breach", "urgent"),
    ("The production system is down", "urgent"),
    ("Our service is unavailable", "urgent"),
    ("How do I change my display name", "routine"),
    ("Please send the installation guide", "routine"),
    ("I would like to update my address", "routine"),
    ("Where can I find the billing history", "routine"),
    ("Thanks for helping with the settings", "routine"),
)
PATTERNS = {
    "reference": r"\b(outage|failed|breach|down)\b",
    "improved": r"\b(outage|failed|breach|down|unavailable)\b",
    "regression": r"\b(outage|breach|down)\b",
}


def produce(run: Path, model: str, *, truncate: bool = False, nonfinite: bool = False) -> dict:
    """Compute predictions and accuracy, close exports, then write the producer report."""

    run.mkdir(parents=True, exist_ok=False)
    dataset = [
        {"id": repeat * len(MESSAGES) + index, "text": text, "label": label}
        for repeat in range(10)
        for index, (text, label) in enumerate(MESSAGES)
    ]
    dataset_bytes = (json.dumps(dataset, sort_keys=True, ensure_ascii=False) + "\n").encode()
    (run / "dataset.json").write_bytes(dataset_bytes)
    pattern = re.compile(PATTERNS[model], re.IGNORECASE)
    predictions = [
        {
            "id": row["id"],
            "label": row["label"],
            "prediction": "urgent" if pattern.search(row["text"]) else "routine",
            "score": "1" if pattern.search(row["text"]) else "0",
        }
        for row in dataset
    ]
    correct = sum(row["prediction"] == row["label"] for row in predictions)
    exported = predictions[:-1] if truncate else predictions
    if nonfinite:
        exported[0] = {**exported[0], "score": "NaN"}
    artifact = run / "artifacts/predictions.csv"
    artifact.parent.mkdir()
    with artifact.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "label", "prediction", "score"])
        writer.writeheader()
        writer.writerows(exported)
    report = {
        "status": "passed",
        "summary": f"Evaluated the {model} keyword classifier on synthetic support messages.",
        "model": model,
        "dataset_sha256": hashlib.sha256(dataset_bytes).hexdigest(),
        "counts": {"examples": len(predictions), "correct": correct},
        "metrics": {"accuracy": correct / len(predictions)},
        "outputs": {"predictions": "artifacts/predictions.csv"},
        "sha256": {"predictions": output_sha256(artifact)},
    }
    write_report_atomic(run / "reports/evaluation.json", report)
    return report


def review(output: Path, case: str) -> int:
    reference = output / "reference"
    candidate = output / case
    if not reference.exists():
        produce(reference, "reference")
    report = produce(
        candidate,
        "regression" if case == "regression" else "improved",
        truncate=case == "truncated",
        nonfinite=case == "nonfinite",
    )
    reviews = output / "reviews" / case
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "evidence_gate.cli",
            "validate",
            "--spec",
            str(FIXTURE / "evidence-gate.yaml"),
            "--run",
            str(candidate),
            "--baseline",
            str(reference),
            "--strict-warnings",
            "--json-out",
            str(reviews / "status.json"),
            "--md-out",
            str(reviews / "review.md"),
            "--junit-out",
            str(reviews / "junit.xml"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode not in (0, 1):
        raise RuntimeError(f"Validation could not run: {completed.stderr.strip()}")
    status = json.loads((reviews / "status.json").read_text(encoding="utf-8"))
    codes = sorted({check["code"] for check in status["checks"] if check["severity"] == "failure"})
    print(
        f"{case}: accuracy={report['metrics']['accuracy']:.2f}; {status['recommendation']}"
        + ("; " + ", ".join(codes) if codes else "")
    )
    return completed.returncode


def run_workflow(output: Path, case: str = "improved", demonstrate_failure: bool = False) -> int:
    output.mkdir(parents=True, exist_ok=False)
    if demonstrate_failure:
        for failed_case in ("regression", "truncated", "nonfinite"):
            if review(output, failed_case) != 1:
                raise RuntimeError(f"Expected {failed_case} to fail its evidence contract")
    code = review(output, case)
    print("Review files: " + str(output / "reviews"))
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New output directory")
    parser.add_argument(
        "--case", choices=["improved", "regression", "truncated", "nonfinite"], default="improved"
    )
    parser.add_argument("--demonstrate-failure", action="store_true")
    args = parser.parse_args(argv)
    if args.demonstrate_failure and args.case != "improved":
        parser.error("--demonstrate-failure requires --case improved")
    try:
        return run_workflow(args.output, args.case, args.demonstrate_failure)
    except (OSError, ValueError, RuntimeError) as exc:
        print("error: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
