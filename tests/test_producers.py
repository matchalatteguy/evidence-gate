from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from evidence_gate.producers import output_sha256, write_report_atomic


def test_digest_covers_exact_binary_bytes_and_detects_changes(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.bin"
    content = bytes(range(256)) * 10001 + b"\x00\xff\n"
    artifact.write_bytes(content)
    digest = output_sha256(artifact)
    assert digest == hashlib.sha256(content).hexdigest()
    assert len(digest) == 64
    artifact.write_bytes(content + b"changed")
    assert output_sha256(artifact) != digest
    artifact.write_bytes(b"")
    assert output_sha256(artifact) == hashlib.sha256(b"").hexdigest()


def test_atomic_report_roundtrips_json_values_and_replaces_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "reports" / "evaluation.json"
    payload = {
        "status": "passed",
        "counts": {"examples": 12},
        "metrics": {"loss": 0.02},
        "outputs": {"table": "artifacts/table.csv"},
        "notes": "é\n\x00",
    }
    assert write_report_atomic(path, payload) == path
    assert json.loads(path.read_text()) == payload
    with path.open("rb") as previous_reader:
        original = previous_reader.read()
        previous_reader.seek(0)
        write_report_atomic(path, {"status": "failed", "counts": {"examples": 0}})
        # Existing readers keep complete prior evidence while new readers see the replacement.
        assert previous_reader.read() == original
    assert json.loads(path.read_text())["status"] == "failed"
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"bad": float("nan")},
        {"nested": [float("inf")]},
        {"nested": {"bad": float("-inf")}},
        {1: "non-string key"},
        {"nested": {False: "non-string key"}},
        {"tuple": (1, 2)},
        {"object": object()},
    ],
)
def test_invalid_json_payload_cannot_damage_an_existing_report(tmp_path: Path, payload) -> None:
    path = tmp_path / "report.json"
    original = b'{"status":"previous"}\n'
    path.write_bytes(original)
    with pytest.raises(ValueError):
        write_report_atomic(path, payload)
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_circular_producer_payload_fails_cleanly_before_writing(tmp_path: Path) -> None:
    payload = {}
    payload["self"] = payload
    path = tmp_path / "report.json"
    with pytest.raises(ValueError, match="circular"):
        write_report_atomic(path, payload)
    assert not path.exists()


def test_failed_atomic_replacement_preserves_prior_report_and_removes_staging(
    tmp_path: Path, monkeypatch
) -> None:
    from evidence_gate import producers

    path = tmp_path / "report.json"
    path.write_bytes(b'{"status":"old"}')

    def denied(*args):
        raise PermissionError("replacement denied")

    monkeypatch.setattr(producers.os, "replace", denied)
    with pytest.raises(PermissionError, match="denied"):
        write_report_atomic(path, {"status": "new"})
    assert path.read_bytes() == b'{"status":"old"}'
    assert list(tmp_path.iterdir()) == [path]
