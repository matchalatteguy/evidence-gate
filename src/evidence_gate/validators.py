from __future__ import annotations

import csv
import hashlib
import math
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

from evidence_gate.baselines import validate_baseline
from evidence_gate.csv_checks import validate_csv
from evidence_gate.json_data import parse_json
from evidence_gate.models import (
    Check,
    EvidenceSpec,
    OutputSpec,
    ReportSpec,
    RunBundle,
    ValidationResult,
)


def validate_run(
    bundle: RunBundle,
    spec: EvidenceSpec,
    *,
    baseline: RunBundle | None = None,
    strict_warnings: bool = False,
) -> ValidationResult:
    checks: list[Check] = []
    if not spec.reports:
        checks.append(_failure("spec.empty", "Contract contains no reports", None, None))
    for report in spec.reports:
        checks.extend(_validate_report(bundle, report, baseline))
    if strict_warnings:
        checks = [
            replace(check, severity="failure", message=f"{check.message} (warnings are errors)")
            if check.severity == "warning"
            else check
            for check in checks
        ]
        failed_reports = {check.report for check in checks if check.severity == "failure"}
        checks = [
            check
            for check in checks
            if check.code != "report.valid" or check.report not in failed_reports
        ]
    failed = sum(1 for check in checks if check.severity == "failure")
    warned = sum(1 for check in checks if check.severity == "warning")
    passed = sum(1 for check in checks if check.severity == "pass")
    return ValidationResult(
        schema_version=spec.schema_version,
        passed=failed == 0,
        recommendation="approved" if failed == 0 else "needs_work",
        checks=checks,
        counts={"passed": passed, "warnings": warned, "failed": failed, "total": len(checks)},
        run_root=bundle.root.name,
    )


def _validate_report(
    bundle: RunBundle, report: ReportSpec, baseline: RunBundle | None
) -> list[Check]:
    checks: list[Check] = []
    try:
        report_path = bundle.resolve_relative(report.path)
    except ValueError as exc:
        return [_failure("path.escape", str(exc), report.name, "<outside-run-root>")]
    display_path = bundle.display_path(report_path)
    if not report_path.exists():
        severity = "failure" if report.required else "warning"
        code = "report.missing" if report.required else "report.optional_missing"
        return [
            Check(code, f"Report {report.name!r} is missing", severity, report.name, display_path)
        ]
    if not report_path.is_file():
        return [
            _failure(
                "report.invalid_json",
                "Report must be a regular JSON file",
                report.name,
                display_path,
            )
        ]
    payload = _load_json_object(report_path)
    if payload is None:
        return [
            _failure(
                "report.invalid_json", "Report must be a JSON object", report.name, display_path
            )
        ]
    checks.append(
        Check("report.present", f"Report {report.name!r} exists", "pass", report.name, display_path)
    )
    checks.extend(_validate_status(payload, report, display_path))
    checks.extend(_validate_required_fields(payload, report, display_path))
    checks.extend(_validate_thresholds(payload, report, "counts", display_path))
    checks.extend(_validate_thresholds(payload, report, "metrics", display_path))
    checks.extend(_validate_numeric_paths(payload, report, display_path))
    checks.extend(_validate_outputs(bundle, payload, report, display_path))
    if report.regressions:
        checks.extend(validate_baseline(bundle, baseline, report, payload, display_path))
    if not any(check.severity == "failure" for check in checks):
        checks.append(
            Check(
                "report.valid",
                f"Report {report.name!r} passed all checks",
                "pass",
                report.name,
                display_path,
            )
        )
    return checks


def _load_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = parse_json(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _validate_status(payload: dict[str, Any], report: ReportSpec, display_path: str) -> list[Check]:
    if report.expected_status is None:
        return []
    actual = payload.get("status")
    if actual == report.expected_status:
        return [Check("report.status", "Report status matched", "pass", report.name, display_path)]
    return [
        _failure(
            "report.status_mismatch",
            f"Expected status {report.expected_status!r}, found {actual!r}",
            report.name,
            display_path,
        )
    ]


def _validate_required_fields(
    payload: dict[str, Any], report: ReportSpec, display_path: str
) -> list[Check]:
    checks: list[Check] = []
    for field in report.required_fields:
        if _get_path(payload, field) is _MISSING:
            checks.append(
                _failure(
                    "field.missing", f"Missing required field {field!r}", report.name, display_path
                )
            )
        else:
            checks.append(
                Check(
                    "field.present",
                    f"Required field {field!r} exists",
                    "pass",
                    report.name,
                    display_path,
                )
            )
    return checks


def _validate_thresholds(
    payload: dict[str, Any], report: ReportSpec, group: str, display_path: str
) -> list[Check]:
    checks: list[Check] = []
    specs = getattr(report, group)
    if not specs:
        return []
    values = payload.get(group, {})
    if not isinstance(values, dict):
        return [
            _failure(f"{group}.invalid", f"{group} must be an object", report.name, display_path)
        ]
    singular = group[:-1]
    for name, limits in specs.items():
        checks.extend(
            _validate_numeric_value(
                values.get(name),
                limits,
                singular,
                name,
                report.name,
                display_path,
                integer=(group == "counts"),
            )
        )
    return checks


def _validate_numeric_paths(
    payload: dict[str, Any], report: ReportSpec, display_path: str
) -> list[Check]:
    checks: list[Check] = []
    for dotted_path, limits in report.numeric.items():
        value = _get_path(payload, dotted_path)
        checks.extend(
            _validate_numeric_value(
                value, limits, "numeric", dotted_path, report.name, display_path
            )
        )
    return checks


def _validate_numeric_value(
    value: Any,
    limits: dict[str, float],
    code_prefix: str,
    name: str,
    report_name: str,
    display_path: str,
    *,
    integer: bool = False,
) -> list[Check]:
    if integer and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
        return [
            _failure(
                f"{code_prefix}.invalid",
                f"{name!r} must be a non-negative integer",
                report_name,
                display_path,
            )
        ]
    if not isinstance(value, int | float) or isinstance(value, bool) or not _is_finite(value):
        return [
            _failure(
                f"{code_prefix}.invalid",
                f"{name!r} must be finite numeric",
                report_name,
                display_path,
            )
        ]
    minimum = limits.get("min")
    maximum = limits.get("max")
    if minimum is not None and value < minimum:
        return [
            _failure(
                f"{code_prefix}.below_min",
                f"{name!r} is below {minimum}",
                report_name,
                display_path,
            )
        ]
    if maximum is not None and value > maximum:
        return [
            _failure(
                f"{code_prefix}.above_max",
                f"{name!r} is above {maximum}",
                report_name,
                display_path,
            )
        ]
    return [
        Check(
            f"{code_prefix}.valid",
            f"{name!r} satisfied thresholds",
            "pass",
            report_name,
            display_path,
        )
    ]


def _validate_outputs(
    bundle: RunBundle, payload: dict[str, Any], report: ReportSpec, display_path: str
) -> list[Check]:
    checks: list[Check] = []
    for output_name, output_spec in report.outputs.items():
        checks.extend(
            _validate_output(bundle, payload, report, output_name, output_spec, display_path)
        )
    return checks


def _validate_output(
    bundle: RunBundle,
    payload: dict[str, Any],
    report: ReportSpec,
    output_name: str,
    output_spec: OutputSpec,
    display_path: str,
) -> list[Check]:
    value = _get_path(payload, output_spec.path_field)
    if value is _MISSING or not isinstance(value, str):
        severity = "failure" if output_spec.required else "warning"
        return [
            Check(
                "artifact.missing",
                f"Output {output_name!r} is not declared",
                severity,
                report.name,
                display_path,
            )
        ]
    try:
        path = bundle.resolve_relative(value)
    except ValueError as exc:
        code = "path.absolute" if Path(value).is_absolute() else "path.escape"
        return [_failure(code, str(exc), report.name, "<outside-run-root>")]
    if not path.exists():
        severity = "failure" if output_spec.required else "warning"
        return [
            Check(
                "artifact.missing",
                f"Output {output_name!r} does not exist",
                severity,
                report.name,
                bundle.display_path(path),
            )
        ]
    if not path.is_file():
        return [
            _failure(
                "artifact.not_file",
                f"Output {output_name!r} must be a file",
                report.name,
                bundle.display_path(path),
            )
        ]
    checks = [
        Check(
            "artifact.present",
            f"Output {output_name!r} exists",
            "pass",
            report.name,
            bundle.display_path(path),
        )
    ]
    if output_spec.csv is not None:
        checks.extend(
            validate_csv(
                path,
                output_spec.csv,
                output_spec.csv_columns,
                payload,
                report.name,
                bundle.display_path(path),
            )
        )
    elif output_spec.csv_columns:
        checks.extend(
            _validate_csv_columns(
                path, output_spec.csv_columns, report.name, bundle.display_path(path)
            )
        )
    if output_spec.sha256_field is not None:
        checks.extend(
            _validate_sha256(
                path,
                _get_path(payload, output_spec.sha256_field),
                output_spec.sha256_field,
                report.name,
                bundle.display_path(path),
            )
        )
    return checks


def _validate_sha256(
    path: Path, expected: Any, field: str, report_name: str, display_path: str
) -> list[Check]:
    if expected is _MISSING:
        return [
            _failure(
                "artifact.sha256_missing",
                f"Expected SHA-256 field {field!r} is missing",
                report_name,
                display_path,
            )
        ]
    if not isinstance(expected, str) or re.fullmatch(r"[0-9a-fA-F]{64}", expected) is None:
        return [
            _failure(
                "artifact.sha256_invalid",
                f"Expected SHA-256 field {field!r} must contain exactly 64 hexadecimal characters",
                report_name,
                display_path,
            )
        ]
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1048576), b""):
                digest.update(chunk)
    except OSError as exc:
        return [
            _failure(
                "artifact.sha256_read_error",
                f"Could not hash output ({type(exc).__name__})",
                report_name,
                display_path,
            )
        ]
    if digest.hexdigest() != expected.lower():
        return [
            _failure(
                "artifact.sha256_mismatch",
                f"Output bytes do not match SHA-256 field {field!r}",
                report_name,
                display_path,
            )
        ]
    return [
        Check("artifact.sha256_match", "Output SHA-256 matched", "pass", report_name, display_path)
    ]


def _validate_csv_columns(
    path: Path, expected_columns: list[str], report_name: str, display_path: str
) -> list[Check]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            header = next(reader, [])
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        return [
            _failure(
                "table.invalid_csv",
                f"CSV could not be read ({type(exc).__name__})",
                report_name,
                display_path,
            )
        ]
    missing = [column for column in expected_columns if column not in header]
    if missing:
        return [
            _failure(
                "table.column_missing",
                f"Missing columns: {', '.join(missing)}",
                report_name,
                display_path,
            )
        ]
    return [Check("table.columns", "CSV columns matched", "pass", report_name, display_path)]


_MISSING = object()


def _is_finite(value: int | float) -> bool:
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _get_path(payload: dict[str, Any], dotted_path: str) -> Any:
    value: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(value, dict) or part not in value:
            return _MISSING
        value = value[part]
    return value


def _failure(code: str, message: str, report: str | None, path: str | None) -> Check:
    return Check(code=code, message=message, severity="failure", report=report, path=path)
