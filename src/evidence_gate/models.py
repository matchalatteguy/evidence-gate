from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

Severity = Literal["pass", "warning", "failure"]


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
        return cls(
            code=str(payload["code"]),
            message=str(payload["message"]),
            severity=payload["severity"],
            report=payload.get("report"),
            path=payload.get("path"),
        )


@dataclass(frozen=True)
class OutputSpec:
    path_field: str
    required: bool = True
    columns: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReportSpec:
    name: str
    path: str
    required: bool = True
    expected_status: str | None = None
    required_fields: list[str] = field(default_factory=list)
    counts: dict[str, dict[str, float]] = field(default_factory=dict)
    metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    outputs: dict[str, OutputSpec] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceSpec:
    reports: list[ReportSpec]


@dataclass(frozen=True)
class RunBundle:
    root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", self.root.resolve())

    def resolve_relative(self, relative_path: str) -> Path:
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
        try:
            return path.resolve().relative_to(self.root).as_posix()
        except ValueError:
            return path.name


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    recommendation: Literal["approved", "needs_work"]
    checks: list[Check]
    counts: dict[str, int]
    run_root: str

    @property
    def failures(self) -> list[Check]:
        return [check for check in self.checks if check.severity == "failure"]

    @property
    def warnings(self) -> list[Check]:
        return [check for check in self.checks if check.severity == "warning"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "recommendation": self.recommendation,
            "counts": self.counts,
            "run_root": self.run_root,
            "checks": [check.to_dict() for check in self.checks],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ValidationResult:
        return cls(
            passed=bool(payload["passed"]),
            recommendation=payload["recommendation"],
            counts={str(key): int(value) for key, value in payload["counts"].items()},
            run_root=str(payload.get("run_root", "")),
            checks=[Check.from_dict(check) for check in payload["checks"]],
        )
