"""Read JSON without silently discarding duplicate object fields."""

from __future__ import annotations

import json
from typing import Any


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def parse_json(text: str) -> Any:
    return json.loads(text, object_pairs_hook=_unique_object)
