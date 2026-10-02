from __future__ import annotations

import json
from pathlib import Path

import pytest

from evidence_gate import RunBundle, SpecValidationError, load_spec, validate_run


def contract(tmp_path: Path, report: dict) -> Path:
    path = tmp_path / "contract.json"
    path.write_text(
        json.dumps({"reports": [{"name": "evaluation", "path": "report.json", **report}]})
    )
    return path


@pytest.mark.parametrize(
    "rules",
    [
        {},
        {"max_decrease": -1},
        {"max_increase": True},
        {"max_decrease": "2%"},
        {"max_increase": float("inf")},
        {"max_increase": None},
        {"maximum": 1},
        [],
    ],
)
def test_regression_contract_rejects_ambiguous_or_invalid_tolerances(tmp_path: Path, rules) -> None:
    with pytest.raises(SpecValidationError):
        load_spec(contract(tmp_path, {"regressions": {"metrics.accuracy": rules}}))


@pytest.mark.parametrize(
    "csv",
    [
        None,
        [],
        {"rows": {}},
        {"rows": {"min": -1}},
        {"rows": {"min": True}},
        {"rows": {"max": 2.5}},
        {"rows": {"min": 2, "max": 1}},
        {"columns": {"score": {"type": "decimal"}}},
        {"columns": {"score": {"type": "string", "min": 1}}},
        {"columns": {"score": {"type": "number", "min": 1, "non_empty": False}}},
        {"columns": {"score": {"type": "integer", "max": 1, "min": 2}}},
        {"row_count_field": "counts..examples"},
        {"row_count_field": " counts.examples"},
        {"columns": {"score": {"nullable": True}}},
    ],
)
def test_csv_contract_rejects_checks_that_cannot_be_enforced(tmp_path: Path, csv) -> None:
    with pytest.raises(SpecValidationError):
        load_spec(
            contract(tmp_path, {"outputs": {"data": {"path_field": "outputs.data", "csv": csv}}})
        )


@pytest.mark.parametrize(
    "fields", [["dataset_sha256"], ["metrics..accuracy"], [""], "dataset_sha256"]
)
def test_identity_contract_requires_regressions_and_valid_fields(tmp_path: Path, fields) -> None:
    with pytest.raises(SpecValidationError):
        load_spec(contract(tmp_path, {"baseline_match_fields": fields}))


def test_integer_thresholds_do_not_round_down_to_neighboring_count(tmp_path: Path) -> None:
    exact_limit = 2**53 + 1
    path = contract(tmp_path, {"counts": {"examples": {"min": exact_limit}}})
    (tmp_path / "report.json").write_text(json.dumps({"counts": {"examples": exact_limit - 1}}))
    spec = load_spec(path)
    assert spec.reports[0].counts["examples"]["min"] == exact_limit
    result = validate_run(RunBundle(tmp_path), spec)
    assert not result.passed
    assert "count.below_min" in {check.code for check in result.failures}
