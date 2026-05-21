from __future__ import annotations

import json
from pathlib import Path

from evidence_gate import RunBundle, load_spec, validate_run


def test_valid_run_bundle_passes(demo_run: tuple[Path, Path]) -> None:
    spec_path, run_path = demo_run

    result = validate_run(RunBundle(run_path), load_spec(spec_path))

    assert result.passed is True
    assert result.failures == []
    assert result.counts["failed"] == 0
    assert any(check.code == "report.valid" for check in result.checks)


def test_missing_required_report_fails_with_stable_code(demo_run: tuple[Path, Path]) -> None:
    spec_path, run_path = demo_run
    (run_path / "reports" / "metrics.json").unlink()

    result = validate_run(RunBundle(run_path), load_spec(spec_path))

    assert result.passed is False
    assert any(check.code == "report.missing" for check in result.failures)


def test_wrong_report_status_fails(demo_run: tuple[Path, Path]) -> None:
    spec_path, run_path = demo_run
    report_path = run_path / "reports" / "metrics.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    payload["status"] = "needs_work"
    report_path.write_text(json.dumps(payload), encoding="utf-8")

    result = validate_run(RunBundle(run_path), load_spec(spec_path))

    assert result.passed is False
    assert any(check.code == "report.status_mismatch" for check in result.failures)


def test_missing_required_field_fails(demo_run: tuple[Path, Path]) -> None:
    spec_path, run_path = demo_run
    report_path = run_path / "reports" / "metrics.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    payload.pop("summary")
    report_path.write_text(json.dumps(payload), encoding="utf-8")

    result = validate_run(RunBundle(run_path), load_spec(spec_path))

    assert result.passed is False
    assert any(check.code == "field.missing" for check in result.failures)


def test_metric_threshold_type_is_validated(demo_run: tuple[Path, Path]) -> None:
    spec_path, run_path = demo_run
    report_path = run_path / "reports" / "metrics.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    payload["metrics"]["accuracy"] = "high"
    report_path.write_text(json.dumps(payload), encoding="utf-8")

    result = validate_run(RunBundle(run_path), load_spec(spec_path))

    assert result.passed is False
    assert any(check.code == "metric.invalid" for check in result.failures)


def test_count_threshold_requires_non_negative_integer(demo_run: tuple[Path, Path]) -> None:
    spec_path, run_path = demo_run
    report_path = run_path / "reports" / "metrics.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    payload["counts"]["examples"] = -1.5
    report_path.write_text(json.dumps(payload), encoding="utf-8")

    result = validate_run(RunBundle(run_path), load_spec(spec_path))

    assert result.passed is False
    assert any(check.code == "count.invalid" for check in result.failures)


def test_output_path_escaping_run_root_fails(demo_run: tuple[Path, Path]) -> None:
    spec_path, run_path = demo_run
    report_path = run_path / "reports" / "metrics.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    payload["outputs"]["predictions"] = "../outside.csv"
    report_path.write_text(json.dumps(payload), encoding="utf-8")

    result = validate_run(RunBundle(run_path), load_spec(spec_path))

    assert result.passed is False
    assert any(check.code == "path.escape" for check in result.failures)


def test_missing_csv_column_fails(demo_run: tuple[Path, Path]) -> None:
    spec_path, run_path = demo_run
    (run_path / "artifacts" / "predictions.csv").write_text("id,label\n1,cat\n", encoding="utf-8")

    result = validate_run(RunBundle(run_path), load_spec(spec_path))

    assert result.passed is False
    assert any(check.code == "table.column_missing" for check in result.failures)


def test_absolute_output_path_is_rejected(demo_run: tuple[Path, Path], tmp_path: Path) -> None:
    spec_path, run_path = demo_run
    report_path = run_path / "reports" / "metrics.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    payload["outputs"]["predictions"] = str(tmp_path / "outside.csv")
    report_path.write_text(json.dumps(payload), encoding="utf-8")

    result = validate_run(RunBundle(run_path), load_spec(spec_path))

    assert result.passed is False
    assert any(check.code == "path.absolute" for check in result.failures)


def test_missing_required_output_artifact_fails(demo_run: tuple[Path, Path]) -> None:
    spec_path, run_path = demo_run
    (run_path / "artifacts" / "predictions.csv").unlink()

    result = validate_run(RunBundle(run_path), load_spec(spec_path))

    assert result.passed is False
    assert any(check.code == "artifact.missing" for check in result.failures)


def test_optional_report_warns_without_failing(demo_run: tuple[Path, Path]) -> None:
    spec_path, run_path = demo_run
    spec_path.write_text(
        spec_path.read_text(encoding="utf-8")
        + """

  - name: diagnostics
    path: reports/diagnostics.json
    required: false
""",
        encoding="utf-8",
    )

    result = validate_run(RunBundle(run_path), load_spec(spec_path))

    assert result.passed is True
    assert any(check.code == "report.optional_missing" for check in result.warnings)
