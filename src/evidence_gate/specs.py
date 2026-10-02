from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import yaml

from evidence_gate.json_data import parse_json
from evidence_gate.models import SUPPORTED_SCHEMA_VERSION, EvidenceSpec, OutputSpec, ReportSpec


class SpecValidationError(ValueError):
    """Raised when an evidence contract is syntactically valid but malformed."""


class _StrictSafeLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        mapping = super().construct_mapping(node, deep=deep)
        seen = set()
        for key_node, _value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate YAML field: {key}", key_node.start_mark
                )
            seen.add(key)
        return mapping


def load_spec(path: Path) -> EvidenceSpec:
    """Load an evidence contract from YAML or JSON.

    Raises:
        SpecValidationError: if the file does not contain a supported contract shape.
        OSError: if the path cannot be read.
    """

    payload = _load_mapping(path)
    _reject_unknown(payload, {"schema_version", "reports"}, "spec")
    schema_version = _schema_version(payload)
    reports_payload = payload.get("reports")
    if not isinstance(reports_payload, list):
        raise SpecValidationError("reports must be a list")
    if not reports_payload:
        raise SpecValidationError("reports must contain at least one report")
    reports = [
        _parse_report(report, f"reports[{index}]") for index, report in enumerate(reports_payload)
    ]
    if len({report.name for report in reports}) != len(reports):
        raise SpecValidationError("report names must be unique")
    return EvidenceSpec(reports=reports, schema_version=schema_version)


def _load_mapping(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
        payload = (
            parse_json(text)
            if path.suffix.lower() == ".json"
            else yaml.load(text, Loader=_StrictSafeLoader)
        )
    except json.JSONDecodeError as exc:
        raise SpecValidationError(f"invalid JSON spec: {exc.msg}") from exc
    except ValueError as exc:
        raise SpecValidationError(f"invalid JSON spec: {exc}") from exc
    except yaml.YAMLError as exc:
        raise SpecValidationError(f"invalid YAML spec: {exc}") from exc
    if not isinstance(payload, dict):
        raise SpecValidationError("spec root must be a mapping")
    return payload


def _schema_version(payload: dict[str, Any]) -> int:
    raw_version = payload.get("schema_version", SUPPORTED_SCHEMA_VERSION)
    if not isinstance(raw_version, int) or isinstance(raw_version, bool):
        raise SpecValidationError("schema_version must be integer 1")
    if raw_version != SUPPORTED_SCHEMA_VERSION:
        raise SpecValidationError(
            f"unsupported schema_version {raw_version!r}; supported versions: {SUPPORTED_SCHEMA_VERSION}"
        )
    return raw_version


def _parse_report(payload: Any, location: str) -> ReportSpec:
    if not isinstance(payload, dict):
        raise SpecValidationError(f"{location} must be a mapping")
    _reject_unknown(
        payload,
        {
            "name",
            "path",
            "required",
            "expected_status",
            "required_fields",
            "counts",
            "metrics",
            "numeric",
            "outputs",
        },
        location,
    )
    outputs_payload = payload.get("outputs", {})
    if not isinstance(outputs_payload, dict):
        raise SpecValidationError(f"{location}.outputs must be a mapping")
    outputs: dict[str, OutputSpec] = {}
    for name, config in outputs_payload.items():
        if not isinstance(name, str) or not name.strip():
            raise SpecValidationError(f"{location}.outputs keys must be non-empty strings")
        output_location = f"{location}.outputs.{name}"
        outputs[str(name)] = _parse_output(config, output_location)
    return ReportSpec(
        name=_required_str(payload, "name", location),
        path=_required_str(payload, "path", location),
        required=_optional_bool(payload, "required", True, f"{location}.required"),
        expected_status=_optional_str(payload, "expected_status", f"{location}.expected_status"),
        required_fields=_string_list(
            payload.get("required_fields", []), f"{location}.required_fields"
        ),
        counts=_thresholds(payload.get("counts", {}), f"{location}.counts"),
        metrics=_thresholds(payload.get("metrics", {}), f"{location}.metrics"),
        numeric=_thresholds(payload.get("numeric", {}), f"{location}.numeric"),
        outputs=outputs,
    )


def _parse_output(payload: Any, location: str) -> OutputSpec:
    if not isinstance(payload, dict):
        raise SpecValidationError(f"{location} must be a mapping")
    _reject_unknown(
        payload, {"path_field", "required", "columns", "csv_columns", "sha256_field"}, location
    )
    if "columns" in payload and "csv_columns" in payload:
        raise SpecValidationError(f"{location} must use only one of columns or csv_columns")
    column_key = "csv_columns" if "csv_columns" in payload else "columns"
    return OutputSpec(
        path_field=_required_str(payload, "path_field", location),
        required=_optional_bool(payload, "required", True, f"{location}.required"),
        csv_columns=_string_list(payload.get(column_key, []), f"{location}.{column_key}"),
        sha256_field=_optional_field_path(payload, "sha256_field", location),
    )


def _optional_field_path(payload: dict[str, Any], key: str, location: str) -> str | None:
    if key not in payload:
        return None
    value = _required_str(payload, key, location)
    if any(not part or part.strip() != part for part in value.split(".")):
        raise SpecValidationError(f"{location}.{key} must name non-empty dotted field components")
    return value


def _reject_unknown(payload: dict, allowed: set[str], location: str) -> None:
    unknown = set(payload) - allowed
    if unknown:
        fields = ", ".join(sorted(map(str, unknown)))
        raise SpecValidationError(f"{location} contains unsupported fields: {fields}")


def _required_str(payload: dict[str, Any], key: str, location: str) -> str:
    value = payload.get(key)
    if value is None:
        raise SpecValidationError(f"{location}.{key} is required")
    if not isinstance(value, str) or not value.strip():
        raise SpecValidationError(f"{location}.{key} must be a non-empty string")
    return value


def _optional_str(payload: dict[str, Any], key: str, location: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise SpecValidationError(f"{location} must be a non-empty string when set")
    return value


def _optional_bool(payload: dict[str, Any], key: str, default: bool, location: str) -> bool:
    value = payload.get(key, default)
    if not isinstance(value, bool):
        raise SpecValidationError(f"{location} must be a boolean")
    return value


def _string_list(value: Any, location: str) -> list[str]:
    if not isinstance(value, list):
        raise SpecValidationError(f"{location} must be a list")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise SpecValidationError(f"{location} must contain only non-empty strings")
    return list(value)


def _thresholds(payload: Any, location: str) -> dict[str, dict[str, float]]:
    if not isinstance(payload, dict):
        raise SpecValidationError(f"{location} must be a mapping")
    thresholds: dict[str, dict[str, float]] = {}
    for name, rules in payload.items():
        threshold_location = f"{location}.{name}"
        if not isinstance(name, str) or not name.strip():
            raise SpecValidationError(f"{location} keys must be non-empty strings")
        if not isinstance(rules, dict):
            raise SpecValidationError(f"{threshold_location} must be a mapping")
        unknown = set(rules) - {"min", "max"}
        if unknown:
            raise SpecValidationError(
                f"{threshold_location} contains unsupported threshold keys: {', '.join(sorted(unknown))}"
            )
        if not rules:
            raise SpecValidationError(f"{threshold_location} must define min, max, or both")
        parsed: dict[str, float] = {}
        for key, value in rules.items():
            if (
                not isinstance(value, int | float)
                or isinstance(value, bool)
                or not _is_finite(value)
            ):
                raise SpecValidationError(f"{threshold_location}.{key} must be finite numeric")
            parsed[str(key)] = float(value)
        thresholds[str(name)] = parsed
        if "min" in parsed and "max" in parsed and parsed["min"] > parsed["max"]:
            raise SpecValidationError(f"{threshold_location}.min must not exceed max")
    return thresholds


def _is_finite(value: int | float) -> bool:
    try:
        return math.isfinite(value)
    except OverflowError:
        return False
