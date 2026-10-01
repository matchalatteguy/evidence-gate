from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

Severity = Literal["pass", "warning", "failure"]
SUPPORTED_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Check:
    code: str
    message: str
    severity: Severity
    report: str | None = None
    path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "report": self.report,
            "path": self.path,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Check:
        if not isinstance(payload, dict):
            raise ValueError("each status check must be an object")
        if not all(isinstance(payload.get(key), str) for key in ("code", "message")):
            raise ValueError("check code and message must be strings")
        if payload.get("severity") not in ("pass", "warning", "failure"):
            raise ValueError("check severity must be pass, warning, or failure")
        for key in ("report", "path"):
            if payload.get(key) is not None and not isinstance(payload[key], str):
                raise ValueError(f"check {key} must be a string or null")
        return cls(
            code=payload["code"],
            message=payload["message"],
            severity=payload["severity"],
            report=payload.get("report"),
            path=payload.get("path"),
        )


@dataclass(frozen=True)
class OutputSpec:
    path_field: str
    required: bool = True
    csv_columns: list[str] = field(default_factory=list)

    @property
    def columns(self) -> list[str]:
        """Backward-compatible alias for CSV header validation columns."""

        return self.csv_columns


@dataclass(frozen=True)
class ReportSpec:
    name: str
    path: str
    required: bool = True
    expected_status: str | None = None
    required_fields: list[str] = field(default_factory=list)
    counts: dict[str, dict[str, float]] = field(default_factory=dict)
    metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    numeric: dict[str, dict[str, float]] = field(default_factory=dict)
    outputs: dict[str, OutputSpec] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceSpec:
    reports: list[ReportSpec]
    schema_version: int = SUPPORTED_SCHEMA_VERSION


@dataclass(frozen=True)
class RunBundle:
    root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", self.root.resolve())

    def resolve_relative(self, relative_path: str) -> Path:
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise ValueError("paths must be non-empty strings")
        candidate = Path(relative_path)
        if candidate.is_absolute():
            raise ValueError("absolute paths are not allowed")
        resolved = (self.root / candidate).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("path escapes run root") from exc
        return resolved

    def display_path(self, path: Path) -> str:
        resolved = path.resolve()
        try:
            return resolved.relative_to(self.root).as_posix()
        except ValueError:
            return "<outside-run-root>"


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    recommendation: Literal["approved", "needs_work"]
    checks: list[Check]
    counts: dict[str, int]
    run_root: str
    schema_version: int = SUPPORTED_SCHEMA_VERSION

    @property
    def failures(self) -> list[Check]:
        return [check for check in self.checks if check.severity == "failure"]

    @property
    def warnings(self) -> list[Check]:
        return [check for check in self.checks if check.severity == "warning"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "passed": self.passed,
            "recommendation": self.recommendation,
            "counts": self.counts,
            "run_root": self.run_root,
            "checks": [check.to_dict() for check in self.checks],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ValidationResult:
        if not isinstance(payload, dict):
            raise ValueError("status JSON must be an object")
        checks = payload["checks"]
        counts = payload["counts"]
        if not isinstance(checks, list):
            raise ValueError("status JSON field 'checks' must be a list")
        if not checks:
            raise ValueError("status JSON must contain at least one check")
        if not isinstance(counts, dict):
            raise ValueError("status JSON field 'counts' must be an object")
        version = payload.get("schema_version", SUPPORTED_SCHEMA_VERSION)
        if type(version) is not int or version != SUPPORTED_SCHEMA_VERSION:
            raise ValueError("unsupported status schema_version")
        passed = payload["passed"]
        if not isinstance(passed, bool):
            raise ValueError("status JSON field 'passed' must be a boolean")
        if not isinstance(payload.get("run_root", ""), str):
            raise ValueError("status JSON field 'run_root' must be a string")
        parsed_checks = [Check.from_dict(check) for check in checks]
        expected_counts = {
            "passed": sum(check.severity == "pass" for check in parsed_checks),
            "warnings": sum(check.severity == "warning" for check in parsed_checks),
            "failed": sum(check.severity == "failure" for check in parsed_checks),
            "total": len(parsed_checks),
        }
        if any(type(value) is not int or value < 0 for value in counts.values()):
            raise ValueError("status counts must be non-negative integers")
        if counts != expected_counts:
            raise ValueError("status counts do not match checks")
        expected_passed = expected_counts["failed"] == 0
        recommendation = "approved" if expected_passed else "needs_work"
        if passed != expected_passed or payload["recommendation"] != recommendation:
            raise ValueError("status decision does not match checks")
        return cls(
            schema_version=version,
            passed=passed,
            recommendation=recommendation,
            counts=expected_counts,
            run_root=payload.get("run_root", ""),
            checks=parsed_checks,
        )
