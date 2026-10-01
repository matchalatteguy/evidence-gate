from __future__ import annotations

import json
from pathlib import Path

import pytest

from evidence_gate import RunBundle, SpecValidationError, load_spec, validate_run
from evidence_gate.cli import main
from evidence_gate.models import EvidenceSpec


@pytest.mark.parametrize(
    "payload, error",
    [
        ({"reports": []}, "at least one report"),
        (
            {
                "reports": [
                    {
                        "name": "metrics",
                        "path": "metrics.json",
                        "metric": {"accuracy": {"min": 0.9}},
                    }
                ]
            },
            "unsupported fields: metric",
        ),
        (
            {"reports": [{"name": "metrics", "path": "metrics.json", "outputs": []}]},
            "outputs must be a mapping",
        ),
        (
            {
                "reports": [
                    {
                        "name": "metrics",
                        "path": "metrics.json",
                        "metrics": {"accuracy": {"min": 1, "max": 0}},
                    }
                ]
            },
            "min must not exceed max",
        ),
        (
            {
                "reports": [
                    {
                        "name": "metrics",
                        "path": "metrics.json",
                        "metrics": {"accuracy": {"min": 10**400}},
                    }
                ]
            },
            "finite numeric",
        ),
        ({"reports": [{"name": "metrics", "path": "metrics.json"}] * 2}, "names must be unique"),
    ],
)
def test_contract_cannot_silently_drop_required_checks(tmp_path: Path, payload, error: str) -> None:
    spec_path = tmp_path / "contract.json"
    spec_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SpecValidationError, match=error):
        load_spec(spec_path)


def test_api_empty_contract_cannot_approve_missing_run(tmp_path: Path) -> None:
    result = validate_run(RunBundle(tmp_path / "missing"), EvidenceSpec(reports=[]))
    assert not result.passed
    assert [check.code for check in result.failures] == ["spec.empty"]


@pytest.mark.parametrize(
    "extension, contents",
    [
        (
            "yaml",
            "reports:\n  - name: metrics\n    path: metrics.json\n    metrics:\n      accuracy:\n        min: 0.95\n        min: 0.05\n",
        ),
        (
            "json",
            '{"reports": [{"name": "metrics", "path": "metrics.json", "metrics": {"accuracy": {"min": 0.95, "min": 0.05}}}]}',
        ),
    ],
)
def test_duplicate_contract_fields_cannot_weaken_thresholds(
    tmp_path: Path, extension: str, contents: str
) -> None:
    spec_path = tmp_path / f"contract.{extension}"
    spec_path.write_text(contents, encoding="utf-8")
    with pytest.raises(SpecValidationError, match="duplicate"):
        load_spec(spec_path)


def test_duplicate_report_metric_is_not_accepted(demo_run: tuple[Path, Path]) -> None:
    spec_path, run_path = demo_run
    report = run_path / "reports" / "metrics.json"
    contents = report.read_text(encoding="utf-8").replace(
        '"accuracy": 0.92', '"accuracy": 0.2, "accuracy": 0.92'
    )
    report.write_text(contents, encoding="utf-8")
    result = validate_run(RunBundle(run_path), load_spec(spec_path))
    assert not result.passed
    assert "report.invalid_json" in [check.code for check in result.failures]


def test_directory_cannot_stand_in_for_exported_artifact(demo_run: tuple[Path, Path]) -> None:
    spec_path, run_path = demo_run
    spec = load_spec(spec_path)
    spec.reports[0].outputs["predictions"].csv_columns.clear()
    report = run_path / "reports" / "metrics.json"
    payload = json.loads(report.read_text(encoding="utf-8"))
    payload["outputs"]["predictions"] = "artifacts"
    report.write_text(json.dumps(payload), encoding="utf-8")
    result = validate_run(RunBundle(run_path), spec)
    assert not result.passed
    assert "artifact.not_file" in [check.code for check in result.failures]


@pytest.mark.parametrize("contents", [b"\xff\xfe", b"{broken JSON}"])
def test_corrupt_report_produces_gate_failure(demo_run: tuple[Path, Path], contents: bytes) -> None:
    spec_path, run_path = demo_run
    (run_path / "reports" / "metrics.json").write_bytes(contents)
    result = validate_run(RunBundle(run_path), load_spec(spec_path))
    assert not result.passed
    assert "report.invalid_json" in [check.code for check in result.failures]


@pytest.mark.parametrize(
    "change",
    [
        "false_string",
        "forged_decision",
        "forged_counts",
        "unknown_severity",
        "wrong_version",
        "empty_checks",
    ],
)
def test_packet_rejects_false_or_inconsistent_approval(
    demo_run: tuple[Path, Path], tmp_path: Path, capsys, change: str
) -> None:
    spec_path, run_path = demo_run
    (run_path / "artifacts" / "predictions.csv").unlink()
    payload = validate_run(RunBundle(run_path), load_spec(spec_path)).to_dict()
    if change == "false_string":
        payload["passed"] = "false"
    elif change == "forged_decision":
        payload.update(passed=True, recommendation="approved")
    elif change == "forged_counts":
        payload["counts"]["failed"] = 0
    elif change == "unknown_severity":
        payload["checks"][0]["severity"] = "ignored"
    elif change == "wrong_version":
        payload["schema_version"] = 99
    else:
        payload.update(
            checks=[],
            counts={"passed": 0, "warnings": 0, "failed": 0, "total": 0},
            passed=True,
            recommendation="approved",
        )
    status = tmp_path / "status.json"
    packet = tmp_path / "packet.md"
    status.write_text(json.dumps(payload), encoding="utf-8")
    assert main(["packet", "--status", str(status), "--md-out", str(packet)]) == 2
    assert "input error:" in capsys.readouterr().err
    assert not packet.exists()
