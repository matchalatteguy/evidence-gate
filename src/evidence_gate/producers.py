"""Small producer helpers for local reports and artifact digests."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any


def output_sha256(path: str | Path) -> str:
    """Hash exact file bytes in bounded chunks, without loading an artifact in memory."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_object_bytes(payload: dict[str, Any]) -> bytes:
    if not isinstance(payload, dict):
        raise ValueError("report payload must be a JSON object")
    try:
        _check_json_value(payload)
    except RecursionError as exc:
        raise ValueError("JSON nesting is too deep or circular") from exc
    return (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
    ).encode("utf-8")


def _check_json_value(value: Any) -> None:
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("JSON object keys must be strings")
        for item in value.values():
            _check_json_value(item)
    elif isinstance(value, list):
        for item in value:
            _check_json_value(item)
    elif value is None or isinstance(value, (str, bool, int)):
        return
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON numbers must be finite")
    else:
        raise ValueError(f"unsupported JSON value type: {type(value).__name__}")


def _write_atomic_bytes(path: str | Path, payload: bytes) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=target.parent, prefix=".evidence-gate-", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return target


def write_report_atomic(path: str | Path, payload: dict[str, Any]) -> Path:
    """Write a finite JSON object using same-directory staging and atomic replacement.

    Serialization errors preserve an existing file. The caller chooses the report
    destination and owns its containment and source-authenticity policy.
    """
    return _write_atomic_bytes(path, _json_object_bytes(payload))
