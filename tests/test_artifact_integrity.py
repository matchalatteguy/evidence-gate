from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from evidence_gate import RunBundle, SpecValidationError, load_spec, validate_run


def _configure_digest(demo_run: tuple[Path, Path], *, optional: bool = False) -> Path:
    spec_path, run = demo_run
    contract = yaml.safe_load(spec_path.read_text())
    config = contract["reports"][0]["outputs"]["predictions"]
    config["sha256_field"] = "sha256.predictions"
    config["required"] = not optional
    spec_path.write_text(yaml.safe_dump(contract))
    artifact = run / "artifacts/predictions.csv"
    _set_expected(run, hashlib.sha256(artifact.read_bytes()).hexdigest())
    return artifact


def _set_expected(run: Path, expected: object) -> None:
    report = run / "reports/metrics.json"
    payload = json.loads(report.read_text())
    payload["sha256"] = {"predictions": expected}
    report.write_text(json.dumps(payload))


def test_digest_matches_multiple_chunks_and_accepts_uppercase(demo_run: tuple[Path, Path]) -> None:
    artifact = _configure_digest(demo_run)
    artifact.write_bytes(b"id,label,score\n" + b"1,cat,0.98\n" * 300000)
    spec_path, run = demo_run
    _set_expected(run, hashlib.sha256(artifact.read_bytes()).hexdigest().upper())
    result = validate_run(RunBundle(run), load_spec(spec_path))
    assert result.passed
    assert "artifact.sha256_match" in [check.code for check in result.checks]


@pytest.mark.parametrize("contents", [b"", b"id,label,score\n", b"id,label,score\n2,dog,0.1\n"])
def test_changed_export_bytes_fail(demo_run: tuple[Path, Path], contents: bytes) -> None:
    artifact = _configure_digest(demo_run)
    artifact.write_bytes(contents)
    spec_path, run = demo_run
    result = validate_run(RunBundle(run), load_spec(spec_path))
    assert not result.passed
    assert "artifact.sha256_mismatch" in [check.code for check in result.failures]


def test_missing_expected_digest_fails(demo_run: tuple[Path, Path]) -> None:
    _configure_digest(demo_run)
    spec_path, run = demo_run
    report = run / "reports/metrics.json"
    payload = json.loads(report.read_text())
    payload.pop("sha256")
    report.write_text(json.dumps(payload))
    result = validate_run(RunBundle(run), load_spec(spec_path))
    assert not result.passed
    assert "artifact.sha256_missing" in [check.code for check in result.failures]


@pytest.mark.parametrize(
    "expected", [None, True, 4, [], "a" * 63, "a" * 65, "g" * 64, " " + "a" * 64]
)
def test_malformed_expected_digest_fails(demo_run: tuple[Path, Path], expected: object) -> None:
    _configure_digest(demo_run)
    spec_path, run = demo_run
    _set_expected(run, expected)
    result = validate_run(RunBundle(run), load_spec(spec_path))
    assert not result.passed
    assert "artifact.sha256_invalid" in [check.code for check in result.failures]


def test_digest_read_error_fails(demo_run: tuple[Path, Path], monkeypatch) -> None:
    artifact = _configure_digest(demo_run)
    spec_path, run = demo_run
    original_open = Path.open

    def denied_binary_read(path, mode="r", *args, **kwargs):
        if path == artifact and mode == "rb":
            raise PermissionError("test denied artifact read")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied_binary_read)
    result = validate_run(RunBundle(run), load_spec(spec_path))
    assert not result.passed
    assert "artifact.sha256_read_error" in [check.code for check in result.failures]


def test_absent_optional_output_keeps_warning_semantics(demo_run: tuple[Path, Path]) -> None:
    artifact = _configure_digest(demo_run, optional=True)
    artifact.unlink()
    spec_path, run = demo_run
    _set_expected(run, None)
    result = validate_run(RunBundle(run), load_spec(spec_path))
    assert result.passed
    assert [check.code for check in result.warnings] == ["artifact.missing"]
    assert not any("sha256" in check.code for check in result.checks)


def test_present_optional_output_still_requires_configured_digest(
    demo_run: tuple[Path, Path],
) -> None:
    _configure_digest(demo_run, optional=True)
    spec_path, run = demo_run
    _set_expected(run, None)
    result = validate_run(RunBundle(run), load_spec(spec_path))
    assert not result.passed
    assert "artifact.sha256_invalid" in [check.code for check in result.failures]


def test_unconfigured_digest_does_not_change_existing_contract(demo_run: tuple[Path, Path]) -> None:
    spec_path, run = demo_run
    _set_expected(run, None)
    result = validate_run(RunBundle(run), load_spec(spec_path))
    assert result.passed
    assert not any("sha256" in check.code for check in result.checks)


@pytest.mark.parametrize(
    "value",
    [None, True, 4, [], "", ".", ".digest", "digest.", "sha..file", "sha. file", " sha.file"],
)
def test_digest_field_spec_must_be_a_nonempty_dotted_path(tmp_path: Path, value: object) -> None:
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(
        json.dumps(
            {
                "reports": [
                    {
                        "name": "metrics",
                        "path": "metrics.json",
                        "outputs": {"data": {"path_field": "outputs.data", "sha256_field": value}},
                    }
                ]
            }
        )
    )
    with pytest.raises(SpecValidationError, match="sha256_field"):
        load_spec(spec_path)
