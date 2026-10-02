from __future__ import annotations

import json
import os
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from evidence_gate.baselines import validate_baseline
from evidence_gate.models import RegressionSpec, ReportSpec, RunBundle


def _runs(tmp_path: Path, reference: object):
    candidate = RunBundle(tmp_path / "candidate")
    baseline = RunBundle(tmp_path / "reference")
    baseline.root.mkdir()
    report = baseline.root / "metrics.json"
    report.write_text(json.dumps(reference), encoding="utf-8")
    return candidate, baseline, report


def _spec(**kwargs):
    return ReportSpec(
        name="evaluation",
        path="metrics.json",
        expected_status="passed",
        regressions={"metrics.error": RegressionSpec(max_increase=0.1)},
        **kwargs,
    )


def _payload(number):
    return {"status": "passed", "metrics": {"error": number}}


def test_unconfigured_baseline_does_not_change_existing_checks(tmp_path):
    candidate = RunBundle(tmp_path / "candidate")
    spec = ReportSpec(name="evaluation", path="metrics.json")
    assert validate_baseline(candidate, None, spec, {}, "metrics.json") == []


def test_reference_is_required_for_configured_regressions(tmp_path):
    candidate = RunBundle(tmp_path / "candidate")
    checks = validate_baseline(candidate, None, _spec(), _payload(0.1), "metrics.json")
    assert [check.code for check in checks] == ["baseline.required"]
    assert checks[0].severity == "failure"


@pytest.mark.parametrize("alias", ["same-path", "dot", "symlink"])
def test_candidate_cannot_be_its_own_reference(tmp_path, alias):
    _, baseline, _ = _runs(tmp_path, _payload(0.1))
    candidate_path = baseline.root
    if alias == "dot":
        candidate_path = candidate_path / "."
    elif alias == "symlink":
        candidate_path = tmp_path / "candidate-alias"
        candidate_path.symlink_to(baseline.root, target_is_directory=True)
    checks = validate_baseline(
        RunBundle(candidate_path), baseline, _spec(), _payload(0.1), "metrics.json"
    )
    assert [check.code for check in checks] == ["baseline.same_run"]
    assert checks[0].severity == "failure"
    assert str(baseline.root) not in json.dumps(checks[0].to_dict())


@pytest.mark.parametrize(
    ("current", "previous", "allowance", "code"),
    [
        (0.4, 0.2, RegressionSpec(max_increase=0.1), "regression.increase"),
        (0.2, 0.4, RegressionSpec(max_decrease=0.1), "regression.decrease"),
        (0.2, 0.4, RegressionSpec(max_increase=0), "regression.valid"),
        (0.4, 0.2, RegressionSpec(max_decrease=0), "regression.valid"),
        (0.3, 0.2, RegressionSpec(max_increase=0.1), "regression.valid"),
        (0.2, 0.3, RegressionSpec(max_decrease=0.1), "regression.valid"),
        (0, 0, RegressionSpec(max_increase=0, max_decrease=0), "regression.valid"),
        (-0.1, -0.3, RegressionSpec(max_increase=0.1), "regression.increase"),
        (-0.3, -0.1, RegressionSpec(max_decrease=0.1), "regression.decrease"),
    ],
)
def test_absolute_directional_regression(tmp_path, current, previous, allowance, code):
    bundle, baseline, _ = _runs(tmp_path, _payload(previous))
    spec = ReportSpec("evaluation", "metrics.json", regressions={"metrics.error": allowance})
    check = validate_baseline(bundle, baseline, spec, _payload(current), "metrics.json")[0]
    assert check.code == code
    assert check.details["candidate"] == current
    assert check.details["baseline"] == previous
    assert Decimal(check.details["delta"]) == Decimal(str(current)) - Decimal(str(previous))
    assert "candidate" in check.message and "baseline" in check.message
    assert "delta" in check.message


def test_delta_preserves_large_integer_increment(tmp_path):
    previous = 10**200
    bundle, baseline, _ = _runs(tmp_path, _payload(previous))
    check = validate_baseline(bundle, baseline, _spec(), _payload(previous + 1), "metrics.json")[0]
    assert check.code == "regression.increase"
    assert check.details["delta"] == "1"
    assert check.details["candidate"] == previous + 1


def test_finite_values_do_not_overflow_when_delta_exceeds_float_range(tmp_path):
    bundle, baseline, _ = _runs(tmp_path, _payload(-1e308))
    spec = ReportSpec(
        "evaluation",
        "metrics.json",
        regressions={"metrics.error": RegressionSpec(max_increase=1e308)},
    )
    check = validate_baseline(bundle, baseline, spec, _payload(1e308), "metrics.json")[0]
    assert check.code == "regression.increase"
    assert Decimal(check.details["delta"]) == Decimal("2e308")
    json.dumps(check.to_dict(), allow_nan=False)


def test_delta_is_exact_and_isolated_from_callers_decimal_context(tmp_path):
    bundle, baseline, _ = _runs(tmp_path, _payload(1.0))
    with localcontext() as caller:
        caller.prec = 2
        caller.Emax = 2
        caller.Emin = -2
        check = validate_baseline(bundle, baseline, _spec(), _payload(1.1), "metrics.json")[0]
        assert caller.prec == 2 and caller.Emax == 2 and caller.Emin == -2
    assert check.code == "regression.valid"
    assert check.details["delta"] == "0.1"


def test_tiny_reference_difference_at_extreme_exponent_does_not_round_to_tolerance(tmp_path):
    bundle, baseline, _ = _runs(tmp_path, _payload(-5e-324))
    spec = ReportSpec(
        "evaluation",
        "metrics.json",
        regressions={"metrics.error": RegressionSpec(max_increase=1e308)},
    )
    check = validate_baseline(bundle, baseline, spec, _payload(1e308), "metrics.json")[0]
    assert check.code == "regression.increase"
    assert Decimal(check.details["delta"]) > Decimal("1e308")


@pytest.mark.parametrize("source", ["candidate", "baseline"])
@pytest.mark.parametrize("value", [None, True, "0.1", float("nan"), float("inf"), [], {}])
def test_missing_or_invalid_numbers_fail_closed(tmp_path, source, value):
    current, previous = _payload(0.1), _payload(0.1)
    (current if source == "candidate" else previous)["metrics"]["error"] = value
    bundle, baseline, _ = _runs(tmp_path, previous)
    checks = validate_baseline(bundle, baseline, _spec(), current, "metrics.json")
    assert [check.code for check in checks] == ["baseline.numeric_invalid"]
    assert checks[0].details["source"] == source
    json.dumps(checks[0].to_dict(), allow_nan=False)


@pytest.mark.parametrize("source", ["candidate", "baseline"])
def test_absent_dotted_numeric_field_fails_closed(tmp_path, source):
    current, previous = _payload(0.1), _payload(0.1)
    (current if source == "candidate" else previous)["metrics"].pop("error")
    bundle, baseline, _ = _runs(tmp_path, previous)
    assert (
        validate_baseline(bundle, baseline, _spec(), current, "metrics.json")[0].code
        == "baseline.numeric_invalid"
    )


def test_missing_reference_report_fails(tmp_path):
    bundle, baseline, report = _runs(tmp_path, _payload(0.1))
    report.unlink()
    assert (
        validate_baseline(bundle, baseline, _spec(), _payload(0.1), "metrics.json")[0].code
        == "baseline.report_missing"
    )


@pytest.mark.parametrize(
    "contents", [b"[]", b"{broken", b"\xff\xfe", b'{"status":"passed","status":"failed"}']
)
def test_invalid_reference_report_fails(tmp_path, contents):
    bundle, baseline, report = _runs(tmp_path, _payload(0.1))
    report.write_bytes(contents)
    assert (
        validate_baseline(bundle, baseline, _spec(), _payload(0.1), "metrics.json")[0].code
        == "baseline.invalid_json"
    )


def test_reference_status_must_match_contract(tmp_path):
    bundle, baseline, _ = _runs(tmp_path, {"status": "failed", "metrics": {"error": 0.1}})
    checks = validate_baseline(bundle, baseline, _spec(), _payload(0.1), "metrics.json")
    assert [check.code for check in checks] == ["baseline.status_mismatch"]


@pytest.mark.parametrize("mode", ["relative-escape", "absolute", "symlink"])
def test_reference_path_escape_fails_without_exposing_absolute_path(tmp_path, mode):
    bundle, baseline, reference = _runs(tmp_path, _payload(0.1))
    outside = tmp_path / "private-absolute-location" / "outside.json"
    outside.parent.mkdir()
    outside.write_text(json.dumps(_payload(0.1)))
    spec = _spec()
    if mode == "symlink":
        reference.unlink()
        reference.symlink_to(outside)
    else:
        spec = ReportSpec(
            "evaluation",
            str(outside) if mode == "absolute" else "../private-absolute-location/outside.json",
            regressions=spec.regressions,
        )
    check = validate_baseline(bundle, baseline, spec, _payload(0.1), "metrics.json")[0]
    assert check.code == "baseline.path_escape"
    assert check.path == "<outside-run-root>"
    assert str(outside) not in json.dumps(check.to_dict())
    assert "private-absolute-location" not in json.dumps(check.to_dict())


def test_unreadable_reference_is_a_failed_check(tmp_path, monkeypatch):
    bundle, baseline, reference = _runs(tmp_path, _payload(0.1))
    original_read = Path.read_text

    def denied(path, *args, **kwargs):
        if path == reference:
            raise PermissionError("private path should not enter diagnostics")
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", denied)
    check = validate_baseline(bundle, baseline, _spec(), _payload(0.1), "metrics.json")[0]
    assert check.code == "baseline.invalid_json"
    assert "private path" not in json.dumps(check.to_dict())


@pytest.mark.parametrize("kind", ["directory", "symlink-loop"])
def test_invalid_reference_file_type_fails_closed(tmp_path, kind):
    bundle, baseline, reference = _runs(tmp_path, _payload(0.1))
    reference.unlink()
    if kind == "directory":
        reference.mkdir()
    else:
        reference.symlink_to(reference.name)
    check = validate_baseline(bundle, baseline, _spec(), _payload(0.1), "metrics.json")[0]
    assert check.severity == "failure"
    # Non-strict Path.resolve and Path.exists classify ELOOP differently across
    # supported Python versions. An unresolved reference must always fail closed.
    expected = {"baseline.invalid_json"}
    if kind == "symlink-loop":
        expected |= {"baseline.path_escape", "baseline.report_missing"}
    assert check.code in expected
    assert str(reference) not in json.dumps(check.to_dict())


@pytest.mark.skipif(os.name != "posix", reason="POSIX named pipe fixture")
def test_baseline_named_pipe_is_not_opened_as_report(tmp_path):
    bundle, baseline, reference = _runs(tmp_path, _payload(0.1))
    reference.unlink()
    os.mkfifo(reference)
    check = validate_baseline(bundle, baseline, _spec(), _payload(0.1), "metrics.json")[0]
    assert check.code == "baseline.invalid_json"


def test_reference_does_not_revalidate_unrelated_contract_requirements(tmp_path):
    bundle, baseline, _ = _runs(tmp_path, _payload(0.1))
    spec = _spec(required_fields=["new_candidate_only_field"])
    checks = validate_baseline(bundle, baseline, spec, _payload(0.1), "metrics.json")
    assert [check.code for check in checks] == ["regression.valid"]


@pytest.mark.parametrize("value", ["dataset-a", True, 3, 0.5])
def test_matching_scalar_context_allows_comparison(tmp_path, value):
    current, previous = _payload(0.1), _payload(0.1)
    current["context"] = previous["context"] = {"dataset": value}
    bundle, baseline, _ = _runs(tmp_path, previous)
    checks = validate_baseline(
        bundle, baseline, _spec(baseline_match_fields=["context.dataset"]), current, "metrics.json"
    )
    assert [check.code for check in checks] == ["baseline.identity_match", "regression.valid"]


@pytest.mark.parametrize(("current", "previous"), [("dataset-b", "dataset-a"), (1, 1.0), (True, 1)])
def test_mismatched_context_blocks_numeric_comparison(tmp_path, current, previous):
    current_report, previous_report = _payload(0.1), _payload(0.1)
    current_report["dataset"], previous_report["dataset"] = current, previous
    bundle, baseline, _ = _runs(tmp_path, previous_report)
    checks = validate_baseline(
        bundle, baseline, _spec(baseline_match_fields=["dataset"]), current_report, "metrics.json"
    )
    assert [check.code for check in checks] == ["baseline.identity_mismatch"]
    assert checks[0].severity == "failure"


@pytest.mark.parametrize("source", ["candidate", "baseline"])
@pytest.mark.parametrize("value", [None, {}, [], float("inf"), float("nan")])
def test_invalid_identity_context_fails_closed(tmp_path, source, value):
    current, previous = _payload(0.1), _payload(0.1)
    current["dataset"] = previous["dataset"] = "dataset-a"
    (current if source == "candidate" else previous)["dataset"] = value
    bundle, baseline, _ = _runs(tmp_path, previous)
    check = validate_baseline(
        bundle, baseline, _spec(baseline_match_fields=["dataset"]), current, "metrics.json"
    )[0]
    assert check.code == "baseline.identity_invalid"
    json.dumps(check.to_dict(), allow_nan=False)


@pytest.mark.parametrize("source", ["candidate", "baseline"])
def test_absent_identity_context_fails_closed(tmp_path, source):
    current, previous = _payload(0.1), _payload(0.1)
    current["dataset"] = previous["dataset"] = "dataset-a"
    (current if source == "candidate" else previous).pop("dataset")
    bundle, baseline, _ = _runs(tmp_path, previous)
    check = validate_baseline(
        bundle, baseline, _spec(baseline_match_fields=["dataset"]), current, "metrics.json"
    )[0]
    assert check.code == "baseline.identity_invalid"


def test_identity_details_do_not_dump_sensitive_or_large_values(tmp_path):
    current, previous = _payload(0.1), _payload(0.1)
    current["dataset"] = "PRIVATE-CANDIDATE/" * 1000
    previous["dataset"] = "PRIVATE-REFERENCE/" * 1000
    bundle, baseline, _ = _runs(tmp_path, previous)
    check = validate_baseline(
        bundle, baseline, _spec(baseline_match_fields=["dataset"]), current, "metrics.json"
    )[0]
    assert check.code == "baseline.identity_mismatch"
    assert len(json.dumps(check.to_dict())) < 500
    assert "PRIVATE" not in json.dumps(check.to_dict())
