"""Opt-in CSV content checks with bounded diagnostics and incremental reads."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from evidence_gate.models import Check, CsvColumnSpec, CsvSpec

_INTEGER = re.compile(r"[+-]?[0-9]+")
_NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_SAMPLE_LIMIT = 5
_MISSING = object()
_MESSAGES = {
    "table.row_width": "CSV records do not match the header width",
    "table.empty_cell": "Required CSV cells are empty",
    "table.invalid_integer": "CSV integer cells must contain signed or unsigned ASCII digits",
    "table.invalid_number": "CSV numeric cells must contain finite ASCII decimal or scientific literals",
    "table.value_below_min": "CSV numeric cells fall below their configured minimum",
    "table.value_above_max": "CSV numeric cells exceed their configured maximum",
}


@dataclass
class _IssueSummary:
    occurrences: int = 0
    first_rows: list[int] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)

    def add(self, row_number: int, column: str | None = None) -> None:
        self.occurrences += 1
        if len(self.first_rows) < _SAMPLE_LIMIT and row_number not in self.first_rows:
            self.first_rows.append(row_number)
        if column is not None and len(self.columns) < _SAMPLE_LIMIT:
            display_column = column[:128]
            if display_column not in self.columns:
                self.columns.append(display_column)

    def details(self) -> dict[str, Any]:
        details = {"occurrences": self.occurrences, "first_rows": self.first_rows}
        if self.columns:
            details["columns"] = self.columns
        return details


def validate_csv(
    path: Path,
    spec: CsvSpec,
    expected_columns: list[str],
    payload: dict[str, Any],
    report_name: str,
    display_path: str,
) -> list[Check]:
    """Validate all CSV records without retaining rows or creating per-row checks.

    ``first_rows`` diagnostics contain physical starting line numbers, including
    the header at line 1. Row counts count data records, including malformed-width
    records, rather than physical lines in quoted multiline cells. A parser/read
    failure makes the count incomplete, so count rules are not evaluated against
    that partial value. Number cells accept signed ASCII decimal/scientific
    literals with surrounding whitespace ignored; integer cells accept only
    signed ASCII digits with no surrounding whitespace. Specs should come from
    the validated contract loader.
    """

    checks: list[Check] = []
    issues: dict[str, _IssueSummary] = {}
    row_count = 0
    next_row_number = 1
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle, strict=True)
            header = next(reader, None)
            if header is None or not header or any(not name.strip() for name in header):
                return [
                    _failure(
                        "table.invalid_header",
                        "CSV must have a non-empty header with no blank column names",
                        report_name,
                        display_path,
                        {"actual_rows": 0, "complete": False},
                    )
                ]
            if len(set(header)) != len(header):
                return [
                    _failure(
                        "table.invalid_header",
                        "CSV header column names must be unique",
                        report_name,
                        display_path,
                        {"actual_rows": 0, "complete": False},
                    )
                ]
            index = {name: position for position, name in enumerate(header)}
            required = set(expected_columns) | set(spec.columns)
            missing = required - index.keys()
            if missing:
                checks.append(
                    _failure(
                        "table.column_missing",
                        "CSV is missing configured columns",
                        report_name,
                        display_path,
                        {
                            "missing_count": len(missing),
                            "columns": [name[:128] for name in sorted(missing)[:_SAMPLE_LIMIT]],
                        },
                    )
                )
            rules = [
                (name, index[name], column)
                for name, column in spec.columns.items()
                if name in index
            ]
            next_row_number = reader.line_num + 1
            for row in reader:
                row_count += 1
                if len(row) != len(header):
                    _record_issue(issues, "table.row_width", next_row_number)
                else:
                    for name, position, column in rules:
                        _validate_cell(row[position], column, name, next_row_number, issues)
                next_row_number = reader.line_num + 1
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        # Exception messages can include input data or local paths. Keep the
        # public diagnostic fixed and identify only the error class and row.
        checks.append(
            _failure(
                "table.invalid_csv",
                "CSV could not be completely read as strict UTF-8 CSV",
                report_name,
                display_path,
                {
                    "error_type": type(exc).__name__,
                    "first_rows": [next_row_number],
                    "actual_rows": row_count,
                    "complete": False,
                },
            )
        )
        checks.extend(_issue_checks(issues, report_name, display_path))
        return checks

    checks.extend(_issue_checks(issues, report_name, display_path))
    if not checks:
        checks.append(
            Check(
                "table.content",
                "CSV header, record widths, and configured cells passed",
                "pass",
                report_name,
                display_path,
                {"actual_rows": row_count, "complete": True},
            )
        )
    checks.extend(_row_count_checks(row_count, spec, payload, report_name, display_path))
    return checks


def _validate_cell(
    value: str,
    column: CsvColumnSpec,
    name: str,
    row_number: int,
    issues: dict[str, _IssueSummary],
) -> None:
    if not value.strip():
        if column.non_empty:
            _record_issue(issues, "table.empty_cell", row_number, name)
        return
    if column.type == "string":
        return
    if column.type == "integer":
        if _INTEGER.fullmatch(value) is None:
            _record_issue(issues, "table.invalid_integer", row_number, name)
            return
    else:
        # Decimal accepts underscores and Unicode digits; these are not the
        # portable decimal/scientific CSV literals the contract promises.
        value = value.strip()
        if _NUMBER.fullmatch(value) is None:
            _record_issue(issues, "table.invalid_number", row_number, name)
            return
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError):
        _record_issue(issues, "table.invalid_number", row_number, name)
        return
    if not number.is_finite():
        _record_issue(issues, "table.invalid_number", row_number, name)
        return
    # Construction and comparison do not round to the ambient Decimal precision.
    if column.min is not None and number < Decimal(str(column.min)):
        _record_issue(issues, "table.value_below_min", row_number, name)
    if column.max is not None and number > Decimal(str(column.max)):
        _record_issue(issues, "table.value_above_max", row_number, name)


def _record_issue(
    issues: dict[str, _IssueSummary], code: str, row_number: int, column: str | None = None
) -> None:
    issues.setdefault(code, _IssueSummary()).add(row_number, column)


def _issue_checks(
    issues: dict[str, _IssueSummary], report_name: str, display_path: str
) -> list[Check]:
    return [
        _failure(code, _MESSAGES[code], report_name, display_path, summary.details())
        for code, summary in issues.items()
    ]


def _row_count_checks(
    actual: int,
    spec: CsvSpec,
    payload: dict[str, Any],
    report_name: str,
    display_path: str,
) -> list[Check]:
    checks: list[Check] = []
    for bound, code, message in (
        ("min", "table.row_count_below_min", "CSV data row count is below the configured minimum"),
        ("max", "table.row_count_above_max", "CSV data row count exceeds the configured maximum"),
    ):
        limit = spec.rows.get(bound)
        if limit is not None and (actual < limit if bound == "min" else actual > limit):
            checks.append(
                _failure(
                    code,
                    message,
                    report_name,
                    display_path,
                    {"actual_rows": actual, "expected": {bound: limit}},
                )
            )
    expected: Any = _MISSING
    if spec.row_count_field is not None:
        expected = _get_path(payload, spec.row_count_field)
        if type(expected) is not int or expected < 0:
            checks.append(
                _failure(
                    "table.row_count_invalid",
                    "Configured producer row count must be a non-negative integer",
                    report_name,
                    display_path,
                    {"actual_rows": actual, "field": spec.row_count_field},
                )
            )
        elif expected != actual:
            checks.append(
                _failure(
                    "table.row_count_mismatch",
                    "CSV data row count does not match the producer report",
                    report_name,
                    display_path,
                    {"actual_rows": actual, "expected_rows": expected},
                )
            )
    if not checks and (spec.rows or spec.row_count_field is not None):
        details: dict[str, Any] = {"actual_rows": actual, "expected": dict(spec.rows)}
        if expected is not _MISSING:
            details["expected_rows"] = expected
        checks.append(
            Check(
                "table.row_count",
                "CSV data row count satisfied the contract",
                "pass",
                report_name,
                display_path,
                details,
            )
        )
    return checks


def _get_path(payload: dict[str, Any], dotted_path: str) -> Any:
    value: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(value, dict) or part not in value:
            return _MISSING
        value = value[part]
    return value


def _failure(
    code: str,
    message: str,
    report_name: str,
    display_path: str,
    details: dict[str, Any],
) -> Check:
    return Check(code, message, "failure", report_name, display_path, details)
