from __future__ import annotations

import importlib.util
import json
from importlib import resources
from pathlib import Path
from xml.etree import ElementTree

import pytest


def example():
    path = Path(__file__).resolve().parents[1] / "examples/model-promotion/run.py"
    spec = importlib.util.spec_from_file_location("promotion_example", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_promotion_workflow_checks_actual_predictions_and_all_output_decisions(
    tmp_path: Path,
) -> None:
    module = example()
    output = tmp_path / "promotion"
    assert module.run_workflow(output, demonstrate_failure=True) == 0
    expected = {
        "regression": (0.80, "regression.decrease"),
        "truncated": (1.0, "table.row_count_mismatch"),
        "nonfinite": (1.0, "table.invalid_number"),
        "improved": (1.0, None),
    }
    reference = json.loads((output / "reference/reports/evaluation.json").read_text())
    assert reference["counts"] == {"examples": 100, "correct": 90}
    for case, (accuracy, failure_code) in expected.items():
        report = json.loads((output / case / "reports/evaluation.json").read_text())
        assert report["metrics"]["accuracy"] == accuracy
        assert (
            report["metrics"]["accuracy"]
            == report["counts"]["correct"] / report["counts"]["examples"]
        )
        review = output / "reviews" / case
        status = json.loads((review / "status.json").read_text())
        assert status["passed"] == (failure_code is None)
        if failure_code:
            assert failure_code in {
                check["code"] for check in status["checks"] if check["severity"] == "failure"
            }
        xml = ElementTree.parse(review / "junit.xml")
        assert len(xml.findall(".//failure")) == status["counts"]["failed"]
        assert f"Decision: {status['recommendation']}" in (review / "review.md").read_text()


def test_promotion_preserves_previous_runs(tmp_path: Path) -> None:
    output = tmp_path / "already-there"
    output.mkdir()
    sentinel = output / "sentinel.txt"
    sentinel.write_text("keep me")
    with pytest.raises(FileExistsError):
        example().run_workflow(output)
    assert sentinel.read_text() == "keep me"


def test_packaged_promotion_example_matches_documented_source() -> None:
    source = Path(__file__).resolve().parents[1] / "examples/model-promotion"
    packaged = resources.files("evidence_gate").joinpath("examples/model-promotion")
    for name in ("run.py", "evidence-gate.yaml", "README.md"):
        assert packaged.joinpath(name).read_bytes() == (source / name).read_bytes()
