from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

from evidence_gate.models import (
    Check,
    EvidenceSpec,
    OutputSpec,
    ReportSpec,
    RunBundle,
    ValidationResult,
)


def validate_run(bundle: RunBundle, spec: EvidenceSpec) -> ValidationResult:
    checks: list[Check] = []
    for report in spec.reports:
        checks.extend(_validate_report(bundle, report))
    failed = sum(1 for check in checks if check.severity == "failure")
    warned = sum(1 for check in checks if check.severity == "warning")
    passed = sum(1 for check in checks if check.severity == "pass")
    return ValidationResult(
        passed=failed == 0,
        recommendation="approved" if failed == 0 else "needs_work",
        checks=checks,
        counts={"passed": passed, "warnings": warned, "failed": failed, "total": len(checks)},
        run_root=bundle.root.name,
    )


def _validate_report(bundle: RunBundle, report: ReportSpec) -> list[Check]:
    checks: list[Check] = []
    try:
        report_path = bundle.resolve_relative(report.path)
    except ValueError as exc:
        return [_failure("path.escape", str(exc), report.name, report.path)]
    display_path = bundle.display_path(report_path)
    if not report_path.exists():
        severity = "failure" if report.required else "warning"
        code = "report.missing" if report.required else "report.optional_missing"
        return [
            Check(code, f"Report {report.name!r} is missing", severity, report.name, display_path)
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
    checks.extend(_validate_outputs(bundle, payload, report, display_path))
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
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
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
    values = payload.get(group, {})
    if not isinstance(values, dict):
        return [
            _failure(f"{group}.invalid", f"{group} must be an object", report.name, display_path)
        ]
    singular = group[:-1]
    for name, limits in specs.items():
        value = values.get(name)
        if group == "counts" and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
            checks.append(
                _failure(
                    f"{singular}.invalid",
                    f"{name!r} must be a non-negative integer",
                    report.name,
                    display_path,
                )
            )
            continue
        if (
            not isinstance(value, int | float)
            or isinstance(value, bool)
            or not math.isfinite(value)
        ):
            checks.append(
                _failure(
                    f"{singular}.invalid",
                    f"{name!r} must be finite numeric",
                    report.name,
                    display_path,
                )
            )
            continue
        minimum = limits.get("min")
        maximum = limits.get("max")
        if minimum is not None and value < minimum:
            checks.append(
                _failure(
                    f"{singular}.below_min",
                    f"{name!r} is below {minimum}",
                    report.name,
                    display_path,
                )
            )
        elif maximum is not None and value > maximum:
            checks.append(
                _failure(
                    f"{singular}.above_max",
                    f"{name!r} is above {maximum}",
                    report.name,
                    display_path,
                )
            )
        else:
            checks.append(
                Check(
                    f"{singular}.valid",
                    f"{name!r} satisfied thresholds",
                    "pass",
                    report.name,
                    display_path,
                )
            )
    return checks


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
        return [_failure(code, str(exc), report.name, value)]
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
    checks = [
        Check(
            "artifact.present",
            f"Output {output_name!r} exists",
            "pass",
            report.name,
            bundle.display_path(path),
        )
    ]
    if output_spec.columns:
        checks.extend(
            _validate_csv_columns(path, output_spec.columns, report.name, bundle.display_path(path))
        )
    return checks


def _validate_csv_columns(
    path: Path, expected_columns: list[str], report_name: str, display_path: str
) -> list[Check]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            header = next(reader, [])
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        return [_failure("table.invalid_csv", f"CSV could not be read: {exc}", report_name, display_path)]
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


def _get_path(payload: dict[str, Any], dotted_path: str) -> Any:
    value: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(value, dict) or part not in value:
            return _MISSING
        value = value[part]
    return value


def _failure(code: str, message: str, report: str | None, path: str | None) -> Check:
    return Check(code=code, message=message, severity="failure", report=report, path=path)
