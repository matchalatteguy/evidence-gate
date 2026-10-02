"""Validate inputs, compare execution assumptions, then check the output bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

from replay_contract_kit import load_manifest, validate_dataset

from evidence_gate import RunBundle, load_spec, validate_run, write_review_packet_file

FIXTURE = Path(__file__).resolve().parent


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_pipeline(output: Path, case: str = "complete", demonstrate_failure: bool = False) -> int:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = output / "input"
    source.mkdir()
    for name in ("events.jsonl", "manifest.json", "scenarios.yaml"):
        shutil.copyfile(FIXTURE / name, source / name)
    events_path = source / "events.jsonl"
    rows = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    if case == "duplicate-event":
        rows.insert(1, rows[0])
    elif case == "missing-markout":
        rows = [
            row
            for row in rows
            if not (
                row["event_type"] == "book"
                and row["instrument_id"] == "ALPHA"
                and row["timestamp"] > 100
            )
        ]
    events_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    contract = validate_dataset(load_manifest(source / "manifest.json"))
    write_json(output / "reports/input-contract.json", contract.to_dict())
    if not contract.passed:
        print("Input contract failed: " + ", ".join(issue.code for issue in contract.failures))
        return 1
    print(f"Input contract: passed ({contract.rows_read} events)")
    artifacts = output / "artifacts"
    artifacts.mkdir()
    command = [
        sys.executable,
        "-m",
        "replay_realism.cli",
        "compare",
        "--events",
        str(events_path),
        "--scenarios",
        str(source / "scenarios.yaml"),
        "--json-out",
        str(artifacts / "comparison.json"),
        "--csv-out",
        str(artifacts / "comparison.csv"),
        "--md-out",
        str(artifacts / "comparison.md"),
    ]
    replay = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if replay.returncode not in (0, 1):
        raise RuntimeError("Replay could not run: " + replay.stderr.strip())
    comparison = json.loads((artifacts / "comparison.json").read_text(encoding="utf-8"))
    coverage = [
        Decimal(scenario["summary"]["markout_coverage"])
        for scenario in comparison["scenarios"]
        if scenario["summary"]["markout_coverage"] is not None
    ]
    output_paths = {
        "input_contract": "reports/input-contract.json",
        "comparison_json": "artifacts/comparison.json",
        "comparison_csv": "artifacts/comparison.csv",
        "comparison_review": "artifacts/comparison.md",
    }
    envelope = {
        "status": "passed" if replay.returncode == 0 else "failed",
        "comparison_schema": comparison["schema_version"],
        "counts": {
            "input_events": contract.rows_read,
            "scenarios": comparison["scenario_count"],
            "gate_failures": comparison["gate_failure_count"],
            "missing_markouts": sum(
                scenario["summary"]["filled_count"] - scenario["summary"]["markout_count"]
                for scenario in comparison["scenarios"]
            ),
        },
        "metrics": {"minimum_markout_coverage": float(min(coverage)) if coverage else 0},
        "outputs": output_paths,
        "sha256": {name: file_sha256(output / path) for name, path in output_paths.items()},
    }
    write_json(output / "reports/pipeline.json", envelope)
    print(
        f"Scenario comparison: {comparison['scenario_count']} profiles; "
        f"{comparison['gate_failure_count']} gate failures"
    )
    spec = load_spec(FIXTURE / "evidence.yaml")
    csv_path = artifacts / "comparison.csv"
    saved_csv = csv_path.read_bytes()
    if demonstrate_failure or case == "missing-export":
        csv_path.unlink()
        incomplete = validate_run(RunBundle(output), spec)
        write_json(output / "reports/incomplete-status.json", incomplete.to_dict())
        assert not incomplete.passed and any(
            c.code == "artifact.missing" for c in incomplete.failures
        )
        print("Missing export: needs_work; artifact.missing")
        if demonstrate_failure:
            csv_path.write_bytes(saved_csv)
    result = validate_run(RunBundle(output), spec)
    write_json(output / "reports/evidence-status.json", result.to_dict())
    write_review_packet_file(result, output / "review.md")
    print(f"Complete bundle: {result.recommendation}")
    print("Review packet: " + str(output / "review.md"))
    return 0 if result.passed else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="A new output directory")
    parser.add_argument(
        "--case",
        choices=["complete", "missing-export", "duplicate-event", "missing-markout"],
        default="complete",
    )
    parser.add_argument("--demonstrate-failure", action="store_true")
    args = parser.parse_args(argv)
    if args.demonstrate_failure and args.case != "complete":
        parser.error("--demonstrate-failure is for the complete case")
    try:
        return run_pipeline(args.output, args.case, args.demonstrate_failure)
    except (OSError, ValueError, RuntimeError) as exc:
        print("error: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
