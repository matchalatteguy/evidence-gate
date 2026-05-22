from __future__ import annotations

import json
from pathlib import Path

import pytest

from evidence_gate import RunBundle, SpecValidationError, load_spec, validate_run


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


def test_output_symlink_escaping_run_root_fails(
    demo_run: tuple[Path, Path], tmp_path: Path
) -> None:
    spec_path, run_path = demo_run
    outside = tmp_path / "outside.csv"
    outside.write_text("id,label,score\n1,cat,0.98\n", encoding="utf-8")
    symlink_path = run_path / "artifacts" / "outside-link.csv"
    symlink_path.symlink_to(outside)
    report_path = run_path / "reports" / "metrics.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    payload["outputs"]["predictions"] = "artifacts/outside-link.csv"
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


def test_unreadable_csv_is_reported_as_validation_failure(demo_run: tuple[Path, Path]) -> None:
    spec_path, run_path = demo_run
    (run_path / "artifacts" / "predictions.csv").write_bytes(b"id,label,score\n\xff\xfe\x00")

    result = validate_run(RunBundle(run_path), load_spec(spec_path))

    assert result.passed is False
    assert any(check.code == "table.invalid_csv" for check in result.failures)


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


def test_multiple_reports_preserve_mixed_failures_and_warnings(demo_run: tuple[Path, Path]) -> None:
    spec_path, run_path = demo_run
    spec_path.write_text(
        spec_path.read_text(encoding="utf-8")
        + """

  - name: required-diagnostics
    path: reports/required-diagnostics.json
    required: true
  - name: optional-diagnostics
    path: reports/optional-diagnostics.json
    required: false
""",
        encoding="utf-8",
    )

    result = validate_run(RunBundle(run_path), load_spec(spec_path))

    assert result.passed is False
    assert result.counts["failed"] == 1
    assert result.counts["warnings"] == 1
    assert any(check.report == "required-diagnostics" for check in result.failures)
    assert any(check.report == "optional-diagnostics" for check in result.warnings)


def test_optional_output_warns_without_failing(demo_run: tuple[Path, Path]) -> None:
    spec_path, run_path = demo_run
    report_path = run_path / "reports" / "metrics.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    payload["outputs"].pop("predictions")
    report_path.write_text(json.dumps(payload), encoding="utf-8")
    spec_path.write_text(
        spec_path.read_text(encoding="utf-8").replace(
            "required: true\n        columns", "required: false\n        columns"
        ),
        encoding="utf-8",
    )

    result = validate_run(RunBundle(run_path), load_spec(spec_path))

    assert result.passed is True
    assert any(check.code == "artifact.missing" for check in result.warnings)


def test_malformed_output_spec_raises_clear_value_error(demo_run: tuple[Path, Path]) -> None:
    spec_path, _run_path = demo_run
    spec_path.write_text(
        """
reports:
  - name: metrics
    path: reports/metrics.json
    outputs:
      predictions: outputs.predictions
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(
        SpecValidationError, match=r"reports\[0\].outputs.predictions must be a mapping"
    ):
        load_spec(spec_path)


def test_missing_report_name_raises_contextual_spec_error(demo_run: tuple[Path, Path]) -> None:
    spec_path, _run_path = demo_run
    spec_path.write_text(
        """
reports:
  - path: reports/metrics.json
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(SpecValidationError, match=r"reports\[0\].name is required"):
        load_spec(spec_path)


def test_invalid_threshold_shape_raises_contextual_spec_error(demo_run: tuple[Path, Path]) -> None:
    spec_path, _run_path = demo_run
    spec_path.write_text(
        """
reports:
  - name: metrics
    path: reports/metrics.json
    metrics:
      accuracy: 0.9
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(
        SpecValidationError, match=r"reports\[0\].metrics.accuracy must be a mapping"
    ):
        load_spec(spec_path)


def test_symlink_output_escaping_run_root_fails(
    demo_run: tuple[Path, Path], tmp_path: Path
) -> None:
    spec_path, run_path = demo_run
    outside_artifact = tmp_path / "outside.csv"
    outside_artifact.write_text("id,label,score\n1,cat,0.99\n", encoding="utf-8")
    linked_artifact = run_path / "artifacts" / "predictions.csv"
    linked_artifact.unlink()
    linked_artifact.symlink_to(outside_artifact)

    result = validate_run(RunBundle(run_path), load_spec(spec_path))

    assert result.passed is False
    assert any(check.code == "path.escape" for check in result.failures)


def test_mixed_reports_count_failures_warnings_and_passes(demo_run: tuple[Path, Path]) -> None:
    spec_path, run_path = demo_run
    spec_path.write_text(
        spec_path.read_text(encoding="utf-8")
        + """

  - name: optional-diagnostics
    path: reports/diagnostics.json
    required: false
  - name: required-summary
    path: reports/summary.json
    required: true
""",
        encoding="utf-8",
    )

    result = validate_run(RunBundle(run_path), load_spec(spec_path))

    assert result.passed is False
    assert result.counts["failed"] == 1
    assert result.counts["warnings"] == 1
    assert any(check.code == "report.optional_missing" for check in result.warnings)
    assert any(
        check.code == "report.missing" and check.report == "required-summary"
        for check in result.failures
    )


def test_schema_version_is_exposed_and_written_to_result(demo_run: tuple[Path, Path]) -> None:
    spec_path, run_path = demo_run
    spec_path.write_text(
        "schema_version: 1\n" + spec_path.read_text(encoding="utf-8"), encoding="utf-8"
    )

    spec = load_spec(spec_path)
    result = validate_run(RunBundle(run_path), spec)

    assert spec.schema_version == 1
    assert result.to_dict()["schema_version"] == 1


def test_unsupported_schema_version_fails_during_spec_loading(demo_run: tuple[Path, Path]) -> None:
    spec_path, _run_path = demo_run
    spec_path.write_text("schema_version: 99\nreports: []\n", encoding="utf-8")

    with pytest.raises(SpecValidationError, match="unsupported schema_version"):
        load_spec(spec_path)


def test_numeric_thresholds_support_arbitrary_dot_paths(demo_run: tuple[Path, Path]) -> None:
    spec_path, run_path = demo_run
    spec_path.write_text(
        spec_path.read_text(encoding="utf-8")
        + """
    numeric:
      diagnostics.sample_count: {min: 20}
""",
        encoding="utf-8",
    )
    report_path = run_path / "reports" / "metrics.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    payload["diagnostics"] = {"sample_count": 24}
    report_path.write_text(json.dumps(payload), encoding="utf-8")

    result = validate_run(RunBundle(run_path), load_spec(spec_path))

    assert result.passed is True
    assert any(check.code == "numeric.valid" for check in result.checks)


def test_numeric_thresholds_fail_on_missing_or_non_numeric_dot_path(
    demo_run: tuple[Path, Path],
) -> None:
    spec_path, run_path = demo_run
    spec_path.write_text(
        spec_path.read_text(encoding="utf-8")
        + """
    numeric:
      diagnostics.sample_count: {min: 20}
""",
        encoding="utf-8",
    )

    result = validate_run(RunBundle(run_path), load_spec(spec_path))

    assert result.passed is False
    assert any(check.code == "numeric.invalid" for check in result.failures)


def test_csv_columns_is_preferred_explicit_output_validator_name(
    demo_run: tuple[Path, Path],
) -> None:
    spec_path, run_path = demo_run
    spec_path.write_text(
        spec_path.read_text(encoding="utf-8").replace(
            "columns: [id, label, score]", "csv_columns: [id, label, score]"
        ),
        encoding="utf-8",
    )

    result = validate_run(RunBundle(run_path), load_spec(spec_path))

    assert result.passed is True
    assert any(check.code == "table.columns" for check in result.checks)


def test_empty_threshold_map_is_rejected_with_context(demo_run: tuple[Path, Path]) -> None:
    spec_path, _run_path = demo_run
    spec_path.write_text(
        """
reports:
  - name: metrics
    path: reports/metrics.json
    numeric:
      diagnostics.sample_count: {}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(
        SpecValidationError,
        match=r"reports\[0\]\.numeric\.diagnostics\.sample_count must define min",
    ):
        load_spec(spec_path)


def test_display_path_redacts_unexpected_outside_root(tmp_path: Path) -> None:
    bundle = RunBundle(tmp_path / "run")

    assert bundle.display_path(tmp_path / "outside.txt") == "<outside-run-root>"
