"""Read JSON without silently discarding duplicate object fields."""

from __future__ import annotations

import json
import math
from decimal import Decimal, InvalidOperation
from typing import Any


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def parse_json(text: str) -> Any:
    try:
        return json.loads(text, object_pairs_hook=_unique_object, parse_float=_roundtrip_float)
    except RecursionError as exc:
        raise ValueError("JSON nesting exceeds the supported parser depth") from exc


def _roundtrip_float(literal: str) -> float:
    """Fail closed if decoding a decimal literal silently changes its stated value.

    Ordinary JSON emitted by Python's float serializer round-trips. Higher-precision
    literals and overflow/underflow require an explicit producer representation,
    rather than becoming an indistinguishable metric or context identity.
    """
    value = float(literal)
    try:
        exact = Decimal(literal)
    except InvalidOperation as exc:
        raise ValueError(
            "numeric literal cannot round-trip without decimal precision loss"
        ) from exc
    if not math.isfinite(value) or not exact.is_finite() or exact != Decimal(str(value)):
        raise ValueError("numeric literal cannot round-trip without decimal precision loss")
    return value
