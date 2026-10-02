"""Compare explicitly selected numeric evidence with a local reference run."""

from __future__ import annotations

import math
from decimal import MAX_EMAX, MIN_EMIN, Decimal, localcontext
from typing import Any

from evidence_gate.json_data import parse_json
from evidence_gate.models import Check, RegressionSpec, ReportSpec, RunBundle

_MISSING = object()


def validate_baseline(
    bundle: RunBundle,
    baseline: RunBundle | None,
    report: ReportSpec,
    candidate: dict[str, Any],
    display_path: str,
) -> list[Check]:
    """Check absolute directional deltas; the reference is not a prior approval claim."""
    if not report.regressions:
        if report.baseline_match_fields:
            return [
                _failure(
                    "baseline.identity_invalid",
                    "Baseline identity matching requires a configured regression comparison",
                    report,
                    display_path,
                )
            ]
        return []
    if baseline is None:
        return [
            _failure(
                "baseline.required",
                "This report configures regressions but no baseline run was supplied",
                report,
                display_path,
            )
        ]
    if bundle.root == baseline.root:
        return [
            _failure(
                "baseline.same_run",
                "The baseline must be a separate run snapshot, not the candidate run itself",
                report,
                display_path,
            )
        ]
    try:
        reference_path = baseline.resolve_relative(report.path)
    except (OSError, RuntimeError, ValueError):
        return [
            _failure(
                "baseline.path_escape",
                "Baseline report path must be relative and contained by the baseline run",
                report,
                "<outside-run-root>",
            )
        ]
    try:
        if not reference_path.is_file():
            missing = not reference_path.exists()
            return [
                _failure(
                    "baseline.report_missing" if missing else "baseline.invalid_json",
                    "Baseline report is missing"
                    if missing
                    else "Baseline report must be a regular JSON file",
                    report,
                    display_path,
                )
            ]
        reference = parse_json(reference_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [
            _failure("baseline.report_missing", "Baseline report is missing", report, display_path)
        ]
    except (OSError, ValueError):
        return [
            _failure(
                "baseline.invalid_json",
                "Baseline report must be a readable JSON object with unique fields",
                report,
                display_path,
            )
        ]
    if not isinstance(reference, dict):
        return [
            _failure(
                "baseline.invalid_json",
                "Baseline report must be a JSON object",
                report,
                display_path,
            )
        ]
    if report.expected_status is not None and reference.get("status") != report.expected_status:
        return [
            _failure(
                "baseline.status_mismatch",
                f"Baseline report status did not match {report.expected_status!r}",
                report,
                display_path,
            )
        ]
    checks = _validate_identity(candidate, reference, report, display_path)
    if any(check.severity == "failure" for check in checks):
        return checks
    for field, allowance in report.regressions.items():
        current, previous = _get_path(candidate, field), _get_path(reference, field)
        current_number, previous_number = _number(current), _number(previous)
        context = {
            "field": field,
            "candidate_run": bundle.root.name,
            "baseline_run": baseline.root.name,
        }
        if current_number is None or previous_number is None:
            invalid = "candidate" if current_number is None else "baseline"
            checks.append(
                _failure(
                    "baseline.numeric_invalid",
                    f"{field!r} must exist as a finite number in the {invalid} report; "
                    "booleans and numeric strings are not accepted",
                    report,
                    display_path,
                    {**context, "source": invalid},
                )
            )
            continue
        checks.extend(
            _compare(
                field,
                current,
                previous,
                current_number,
                previous_number,
                allowance,
                report,
                display_path,
                context,
            )
        )
    return checks


def _validate_identity(
    candidate: dict[str, Any], reference: dict[str, Any], report: ReportSpec, display_path: str
) -> list[Check]:
    checks = []
    for field in report.baseline_match_fields:
        current, previous = _get_path(candidate, field), _get_path(reference, field)
        details = {
            "field": field,
            "candidate_type": _kind(current),
            "baseline_type": _kind(previous),
        }
        if not _identity_scalar(current) or not _identity_scalar(previous):
            checks.append(
                _failure(
                    "baseline.identity_invalid",
                    f"Baseline identity field {field!r} must exist as a non-null finite scalar "
                    "in both reports",
                    report,
                    display_path,
                    details,
                )
            )
        elif type(current) is not type(previous) or current != previous:
            checks.append(
                _failure(
                    "baseline.identity_mismatch",
                    f"Baseline identity field {field!r} differs in type or value",
                    report,
                    display_path,
                    details,
                )
            )
        else:
            checks.append(
                Check(
                    "baseline.identity_match",
                    f"Baseline identity field {field!r} matched",
                    "pass",
                    report.name,
                    display_path,
                    details,
                )
            )
    return checks


def _identity_scalar(value: Any) -> bool:
    return type(value) in (str, bool, int) or (type(value) is float and math.isfinite(value))


def _kind(value: Any) -> str:
    if value is _MISSING:
        return "missing"
    return {
        type(None): "null",
        str: "string",
        bool: "boolean",
        int: "integer",
        float: "number",
        dict: "object",
        list: "array",
    }.get(type(value), "other")


def _compare(
    field: str,
    current: int | float,
    previous: int | float,
    current_number: Decimal,
    previous_number: Decimal,
    allowance: RegressionSpec,
    report: ReportSpec,
    display_path: str,
    context: dict[str, Any],
) -> list[Check]:
    limits = {
        "increase": _number(allowance.max_increase) if allowance.max_increase is not None else None,
        "decrease": _number(allowance.max_decrease) if allowance.max_decrease is not None else None,
    }
    if all(value is None for value in limits.values()) or any(
        value is not None and (limits[direction] is None or limits[direction] < 0)
        for direction, value in (
            ("increase", allowance.max_increase),
            ("decrease", allowance.max_decrease),
        )
    ):
        return [
            _failure(
                "baseline.numeric_invalid",
                f"Regression allowance for {field!r} must configure a finite non-negative limit",
                report,
                display_path,
                {**context, "source": "allowance"},
            )
        ]
    numbers = [current_number, previous_number, *(v for v in limits.values() if v is not None)]
    precision = max(
        80, max(v.adjusted() for v in numbers) - min(v.as_tuple().exponent for v in numbers) + 4
    )
    with localcontext() as arithmetic:
        # Keep every decimal place during subtraction, including extreme finite
        # float exponents and integer deltas too small for float conversion.
        arithmetic.prec = precision
        arithmetic.Emax, arithmetic.Emin, arithmetic.clamp = MAX_EMAX, MIN_EMIN, 0
        delta = current_number - previous_number
        evidence = {
            **context,
            "candidate": current,
            "baseline": previous,
            "delta": str(delta),
            **{
                "max_" + direction: str(limit)
                for direction, limit in limits.items()
                if limit is not None
            },
        }
        for direction, change in (("increase", delta), ("decrease", -delta)):
            limit = limits[direction]
            if limit is not None and change > limit:
                return [
                    _failure(
                        "regression." + direction,
                        f"{field!r}: candidate {current_number}, baseline {previous_number}, "
                        f"delta {delta}; {direction} {change} exceeds allowed {limit}",
                        report,
                        display_path,
                        {**evidence, "direction": direction, "tolerance": str(limit)},
                    )
                ]
    allowed = ", ".join(
        f"maximum {direction} {limit}" for direction, limit in limits.items() if limit is not None
    )
    return [
        Check(
            "regression.valid",
            f"{field!r}: candidate {current_number}, baseline {previous_number}, "
            f"delta {delta}; within {allowed}",
            "pass",
            report.name,
            display_path,
            evidence,
        )
    ]


def _number(value: Any) -> Decimal | None:
    if type(value) not in (int, float) or (isinstance(value, float) and not math.isfinite(value)):
        return None
    try:
        return Decimal(str(value))
    except ValueError:
        return None


def _get_path(payload: dict[str, Any], path: str) -> Any:
    value: Any = payload
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            return _MISSING
        value = value[key]
    return value


def _failure(
    code: str,
    message: str,
    report: ReportSpec,
    path: str,
    details: dict[str, Any] | None = None,
) -> Check:
    return Check(code, message, "failure", report.name, path, details)
