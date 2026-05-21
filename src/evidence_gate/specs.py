from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from evidence_gate.models import EvidenceSpec, OutputSpec, ReportSpec


def load_spec(path: Path) -> EvidenceSpec:
    payload = _load_mapping(path)
    reports_payload = payload.get("reports")
    if not isinstance(reports_payload, list):
        raise ValueError("spec must contain a reports list")
    reports = [_parse_report(report) for report in reports_payload]
    return EvidenceSpec(reports=reports)


def _load_mapping(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    payload = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    if not isinstance(payload, dict):
        raise ValueError("spec root must be a mapping")
    return payload


def _parse_report(payload: dict[str, Any]) -> ReportSpec:
    if not isinstance(payload, dict):
        raise ValueError("each report spec must be a mapping")
    outputs_payload = payload.get("outputs", {}) or {}
    if not isinstance(outputs_payload, dict):
        raise ValueError("report outputs must be a mapping")
    outputs = {
        str(name): OutputSpec(
            path_field=str(config["path_field"]),
            required=bool(config.get("required", True)),
            columns=[str(column) for column in config.get("columns", [])],
        )
        for name, config in outputs_payload.items()
    }
    return ReportSpec(
        name=str(payload["name"]),
        path=str(payload["path"]),
        required=bool(payload.get("required", True)),
        expected_status=payload.get("expected_status"),
        required_fields=[str(field) for field in payload.get("required_fields", [])],
        counts=_thresholds(payload.get("counts", {}) or {}),
        metrics=_thresholds(payload.get("metrics", {}) or {}),
        outputs=outputs,
    )


def _thresholds(payload: dict[str, Any]) -> dict[str, dict[str, float]]:
    if not isinstance(payload, dict):
        raise ValueError("threshold groups must be mappings")
    return {
        str(name): {str(key): float(value) for key, value in rules.items()}
        for name, rules in payload.items()
    }
