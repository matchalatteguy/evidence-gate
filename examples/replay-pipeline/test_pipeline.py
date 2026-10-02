from __future__ import annotations

import json

import pytest
from run import FIXTURE, run_pipeline

from evidence_gate import RunBundle, load_spec, validate_run


def test_complete_run_checks_real_outputs_and_missing_export(tmp_path):
    output = tmp_path / "run"
    assert run_pipeline(output, demonstrate_failure=True) == 0
    incomplete = json.loads((output / "reports/incomplete-status.json").read_text())
    assert incomplete["passed"] is False
    assert any(c["code"] == "artifact.missing" for c in incomplete["checks"])
    final = json.loads((output / "reports/evidence-status.json").read_text())
    assert final["passed"] is True
    assert sum(check["code"] == "artifact.sha256_match" for check in final["checks"]) == 4
    comparison = json.loads((output / "artifacts/comparison.json").read_text())
    assert comparison["scenario_count"] == 3
    assert comparison["decision_count"] == 3
    assert comparison["gate_failure_count"] == 0
    # The trial changes actual execution, rather than just renaming the profile.
    assert (
        comparison["scenarios"][0]["summary"]["filled_count"]
        > comparison["scenarios"][2]["summary"]["filled_count"]
    )
    assert "approved" in (output / "review.md").read_text()


def test_duplicate_event_stops_before_replay(tmp_path):
    output = tmp_path / "run"
    assert run_pipeline(output, "duplicate-event") == 1
    report = json.loads((output / "reports/input-contract.json").read_text())
    assert report["passed"] is False
    assert any(issue["code"] == "duplicate_event" for issue in report["failures"])
    assert not (output / "artifacts/comparison.json").exists()


def test_missing_export_fails_even_when_metrics_pass(tmp_path):
    output = tmp_path / "run"
    assert run_pipeline(output, "missing-export") == 1
    envelope = json.loads((output / "reports/pipeline.json").read_text())
    assert envelope["status"] == "passed"
    status = json.loads((output / "reports/evidence-status.json").read_text())
    assert status["passed"] is False
    assert any(c["code"] == "artifact.missing" for c in status["checks"])


def test_missing_future_evidence_cannot_be_promoted(tmp_path):
    output = tmp_path / "run"
    assert run_pipeline(output, "missing-markout") == 1
    input_report = json.loads((output / "reports/input-contract.json").read_text())
    assert input_report["passed"] is True
    comparison = json.loads((output / "artifacts/comparison.json").read_text())
    assert comparison["gate_failure_count"] > 0
    status = json.loads((output / "reports/evidence-status.json").read_text())
    assert status["passed"] is False


def test_existing_output_directory_is_not_overwritten(tmp_path):
    output = tmp_path / "run"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("keep")
    try:
        run_pipeline(output)
    except FileExistsError:
        pass
    else:
        raise AssertionError("existing output directory was accepted")
    assert marker.read_text() == "keep"


def test_header_only_csv_cannot_be_promoted(tmp_path):
    output = tmp_path / "run"
    assert run_pipeline(output) == 0
    path = output / "artifacts/comparison.csv"
    path.write_text(path.read_text().splitlines()[0] + "\n")
    result = validate_run(RunBundle(output), load_spec(FIXTURE / "evidence.yaml"))
    assert not result.passed
    assert [check.code for check in result.failures] == ["artifact.sha256_mismatch"]


@pytest.mark.parametrize(
    "relative",
    ["artifacts/comparison.json", "artifacts/comparison.md", "reports/input-contract.json"],
)
@pytest.mark.parametrize("contents", [b"", b"tampered evidence\n"])
def test_empty_or_tampered_evidence_cannot_be_promoted(tmp_path, relative, contents):
    output = tmp_path / "run"
    assert run_pipeline(output) == 0
    (output / relative).write_bytes(contents)
    result = validate_run(RunBundle(output), load_spec(FIXTURE / "evidence.yaml"))
    assert not result.passed
    assert [check.code for check in result.failures] == ["artifact.sha256_mismatch"]
