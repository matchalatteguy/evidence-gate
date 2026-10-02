from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from evidence_gate import RunBundle, SpecValidationError, load_spec, validate_run
from evidence_gate.json_data import parse_json


@pytest.mark.parametrize(
    "literal",
    ["0.100000000000000005", "1.0000000000000001", "1e-999", "1e999", "0e999999999999999999999999"],
)
def test_json_does_not_silently_collapse_numeric_evidence(literal: str) -> None:
    with pytest.raises(ValueError, match="precision loss"):
        parse_json('{"value":' + literal + "}")


def test_native_float_serialization_still_round_trips() -> None:
    values = [0.1, 0.1 + 0.2, 1e-300, 1e300, 5e-324, -0.0, 1.2345678901234567]
    assert parse_json(json.dumps(values)) == values


def test_deep_invalid_contract_returns_a_controlled_input_error(tmp_path: Path, capsys) -> None:
    from evidence_gate.cli import main

    # Older decoders hit their recursion limit; newer decoders can parse this
    # valid JSON but must still reject its non-mapping contract root.
    path = tmp_path / "contract.json"
    path.write_text("[" * 10000 + "0" + "]" * 10000)
    assert main(["check-spec", "--spec", str(path)]) == 2
    error = capsys.readouterr().err
    assert "spec error:" in error
    assert "Traceback" not in error


@pytest.mark.parametrize("suffix", ["yaml", "json"])
def test_contract_rejects_precision_losing_tolerance(tmp_path: Path, suffix: str) -> None:
    path = tmp_path / f"contract.{suffix}"
    if suffix == "yaml":
        path.write_text(
            "reports:\n- name: evaluation\n  path: report.json\n  regressions:\n    metrics.value: {max_increase: 0.100000000000000005}\n"
        )
    else:
        path.write_text(
            '{"reports":[{"name":"evaluation","path":"report.json","regressions":{"metrics.value":{"max_increase":0.100000000000000005}}}]}'
        )
    with pytest.raises(SpecValidationError, match="precision"):
        load_spec(path)


def test_lossy_baseline_identity_and_metric_cannot_approve(tmp_path: Path) -> None:
    candidate, reference = tmp_path / "candidate", tmp_path / "reference"
    candidate.mkdir()
    reference.mkdir()
    path = tmp_path / "contract.yaml"
    path.write_text(
        "reports:\n- name: evaluation\n  path: report.json\n  baseline_match_fields: [identity]\n  regressions:\n    metrics.value: {max_increase: 0}\n"
    )
    (candidate / "report.json").write_text(
        '{"metrics":{"value":0.100000000000000005},"identity":1.0000000000000001}'
    )
    (reference / "report.json").write_text('{"metrics":{"value":0.1},"identity":1.0}')
    result = validate_run(RunBundle(candidate), load_spec(path), baseline=RunBundle(reference))
    assert not result.passed
    assert "report.invalid_json" in {check.code for check in result.failures}


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX named pipes only")
def test_fifo_report_fails_without_waiting_for_a_writer(tmp_path: Path) -> None:
    path = tmp_path / "contract.yaml"
    path.write_text("reports:\n- name: evaluation\n  path: report.json\n")
    os.mkfifo(tmp_path / "report.json")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "evidence_gate.cli",
            "validate",
            "--spec",
            str(path),
            "--run",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert completed.returncode == 1
    assert "report.invalid_json" in completed.stdout


def test_escaping_path_diagnostics_do_not_reveal_local_absolute_paths(tmp_path: Path) -> None:
    secret = tmp_path / "private-user-directory" / "metrics.json"
    path = tmp_path / "contract.json"
    path.write_text(json.dumps({"reports": [{"name": "evaluation", "path": str(secret)}]}))
    result = validate_run(RunBundle(tmp_path), load_spec(path))
    assert not result.passed
    assert str(secret) not in json.dumps(result.to_dict())


def test_strict_optional_output_cannot_retain_a_passed_report_summary(tmp_path: Path) -> None:
    path = tmp_path / "contract.json"
    path.write_text(
        json.dumps(
            {
                "reports": [
                    {
                        "name": "evaluation",
                        "path": "report.json",
                        "outputs": {"note": {"path_field": "outputs.note", "required": False}},
                    }
                ]
            }
        )
    )
    (tmp_path / "report.json").write_text('{"outputs":{"note":"missing.txt"}}')
    spec = load_spec(path)
    normal = validate_run(RunBundle(tmp_path), spec)
    assert normal.passed and normal.warnings
    strict = validate_run(RunBundle(tmp_path), spec, strict_warnings=True)
    assert not strict.passed
    assert "artifact.missing" in {check.code for check in strict.failures}
    assert "report.valid" not in {check.code for check in strict.checks}
