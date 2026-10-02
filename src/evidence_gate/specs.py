from __future__ import annotations

import json
import math
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml

from evidence_gate.json_data import parse_json
from evidence_gate.models import (
    SUPPORTED_SCHEMA_VERSION,
    CsvColumnSpec,
    CsvSpec,
    EvidenceSpec,
    OutputSpec,
    RegressionSpec,
    ReportSpec,
)


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

    def construct_yaml_float(self, node):
        value = super().construct_yaml_float(node)
        if math.isfinite(value):
            try:
                exact = Decimal(node.value.replace("_", ""))
            except InvalidOperation as exc:
                raise yaml.constructor.ConstructorError(
                    None, None, "use ordinary decimal/scientific numeric literals", node.start_mark
                ) from exc
            if exact != Decimal(str(value)):
                raise yaml.constructor.ConstructorError(
                    None, None, "numeric literal loses decimal precision", node.start_mark
                )
        return value


_StrictSafeLoader.add_constructor("tag:yaml.org,2002:float", _StrictSafeLoader.construct_yaml_float)


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
    except RecursionError as exc:
        raise SpecValidationError("spec nesting exceeds the supported parser depth") from exc
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
            "regressions",
            "baseline_match_fields",
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
    regressions = _regressions(payload.get("regressions", {}), f"{location}.regressions")
    match_fields = _string_list(
        payload.get("baseline_match_fields", []), f"{location}.baseline_match_fields"
    )
    if match_fields and not regressions:
        raise SpecValidationError(f"{location}.baseline_match_fields requires regressions")
    if any(
        any(not part or part.strip() != part for part in name.split(".")) for name in match_fields
    ):
        raise SpecValidationError(
            f"{location}.baseline_match_fields must contain dotted field paths"
        )
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
        regressions=regressions,
        baseline_match_fields=match_fields,
    )


def _parse_output(payload: Any, location: str) -> OutputSpec:
    if not isinstance(payload, dict):
        raise SpecValidationError(f"{location} must be a mapping")
    _reject_unknown(
        payload,
        {"path_field", "required", "columns", "csv_columns", "sha256_field", "csv"},
        location,
    )
    if "columns" in payload and "csv_columns" in payload:
        raise SpecValidationError(f"{location} must use only one of columns or csv_columns")
    column_key = "csv_columns" if "csv_columns" in payload else "columns"
    return OutputSpec(
        path_field=_required_str(payload, "path_field", location),
        required=_optional_bool(payload, "required", True, f"{location}.required"),
        csv_columns=_string_list(payload.get(column_key, []), f"{location}.{column_key}"),
        sha256_field=_optional_field_path(payload, "sha256_field", location),
        csv=_parse_csv(payload["csv"], f"{location}.csv") if "csv" in payload else None,
    )


def _parse_csv(payload: Any, location: str) -> CsvSpec:
    if not isinstance(payload, dict):
        raise SpecValidationError(f"{location} must be a mapping")
    _reject_unknown(payload, {"rows", "row_count_field", "columns"}, location)
    rows = payload.get("rows", {})
    if not isinstance(rows, dict):
        raise SpecValidationError(f"{location}.rows must be a mapping")
    _reject_unknown(rows, {"min", "max"}, f"{location}.rows")
    if "rows" in payload and not rows:
        raise SpecValidationError(f"{location}.rows must define min, max, or both")
    if any(type(value) is not int or value < 0 for value in rows.values()):
        raise SpecValidationError(f"{location}.rows limits must be non-negative integers")
    if "min" in rows and "max" in rows and rows["min"] > rows["max"]:
        raise SpecValidationError(f"{location}.rows.min must not exceed max")
    columns = payload.get("columns", {})
    if not isinstance(columns, dict):
        raise SpecValidationError(f"{location}.columns must be a mapping")
    parsed_columns: dict[str, CsvColumnSpec] = {}
    for name, rules in columns.items():
        column_location = f"{location}.columns.{name}"
        if not isinstance(name, str) or not name.strip():
            raise SpecValidationError(f"{location}.columns keys must be non-empty strings")
        if not isinstance(rules, dict):
            raise SpecValidationError(f"{column_location} must be a mapping")
        _reject_unknown(rules, {"type", "non_empty", "min", "max"}, column_location)
        column_type = rules.get("type", "string")
        if column_type not in ("string", "integer", "number"):
            raise SpecValidationError(f"{column_location}.type must be string, integer, or number")
        non_empty = _optional_bool(rules, "non_empty", True, f"{column_location}.non_empty")
        limits = {key: rules[key] for key in ("min", "max") if key in rules}
        if limits:
            if column_type == "string":
                raise SpecValidationError(
                    f"{column_location} numeric limits require a numeric type"
                )
            if not non_empty:
                raise SpecValidationError(
                    f"{column_location} numeric limits require non_empty: true"
                )
            limits = _thresholds({name: limits}, f"{location}.columns")[name]
        parsed_columns[name] = CsvColumnSpec(
            type=column_type, non_empty=non_empty, min=limits.get("min"), max=limits.get("max")
        )
    return CsvSpec(
        rows=dict(rows),
        row_count_field=_optional_field_path(payload, "row_count_field", location),
        columns=parsed_columns,
    )


def _regressions(payload: Any, location: str) -> dict[str, RegressionSpec]:
    if not isinstance(payload, dict):
        raise SpecValidationError(f"{location} must be a mapping")
    parsed: dict[str, RegressionSpec] = {}
    for name, rules in payload.items():
        if not isinstance(name, str) or any(
            not part or part.strip() != part for part in name.split(".")
        ):
            raise SpecValidationError(f"{location} keys must be non-empty dotted field paths")
        rule_location = f"{location}.{name}"
        if not isinstance(rules, dict):
            raise SpecValidationError(f"{rule_location} must be a mapping")
        _reject_unknown(rules, {"max_increase", "max_decrease"}, rule_location)
        if not rules:
            raise SpecValidationError(f"{rule_location} must define max_increase or max_decrease")
        for value in rules.values():
            if type(value) not in (int, float) or not _is_finite(value) or value < 0:
                raise SpecValidationError(
                    f"{rule_location} tolerances must be finite non-negative numbers"
                )
        parsed[name] = RegressionSpec(**rules)
    return parsed


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
                f"{threshold_location} contains unsupported threshold keys: {', '.join(sorted(map(str, unknown)))}"
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
            parsed[str(key)] = value
        thresholds[str(name)] = parsed
        if "min" in parsed and "max" in parsed and parsed["min"] > parsed["max"]:
            raise SpecValidationError(f"{threshold_location}.min must not exceed max")
    return thresholds


def _is_finite(value: int | float) -> bool:
    try:
        return math.isfinite(value)
    except OverflowError:
        return False
