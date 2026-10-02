from __future__ import annotations

import json
import os
import shutil
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from evidence_gate.cli import main
from evidence_gate.models import Check, RunBundle, ValidationResult
from evidence_gate.reports import render_junit_xml, render_review_packet, write_junit_xml
from evidence_gate.specs import load_spec
from evidence_gate.validators import validate_run


def arguments(spec, run, *options):
    return ["validate", "--spec", str(spec), "--run", str(run), *options]


def combined_paths(tmp_path):
    outputs = [
        tmp_path / "ci" / "status.json",
        tmp_path / "ci" / "packet.md",
        tmp_path / "ci" / "junit.xml",
    ]
    options = [
        "--json-out",
        str(outputs[0]),
        "--md-out",
        str(outputs[1]),
        "--junit-out",
        str(outputs[2]),
    ]
    return outputs, options


def assert_consistent_outputs(outputs, expected_passed):
    status = json.loads(outputs[0].read_text())
    xml = ET.fromstring(outputs[2].read_text())
    suite = xml.find("testsuite")
    assert status["passed"] is expected_passed
    expected_decision = "approved" if expected_passed else "needs_work"
    assert status["recommendation"] == expected_decision
    assert f"Decision: {expected_decision}" in outputs[1].read_text()
    assert int(xml.attrib["tests"]) == len(status["checks"])
    assert int(xml.attrib["failures"]) == status["counts"]["failed"]
    assert int(xml.attrib["skipped"]) == status["counts"]["warnings"]
    assert suite.attrib == {"name": "evidence-gate", **xml.attrib}
    cases = suite.findall("testcase")
    assert len(cases) == len(status["checks"])
    for index, (case, check) in enumerate(zip(cases, status["checks"], strict=True), start=1):
        assert case.attrib["name"] == f"{index:04d}: {check['code']}"
        assert case.find("properties/property[@name='code']").attrib["value"] == check["code"]
        assert case.attrib["classname"] == (check["report"] or "evidence-gate")
        assert (case.find("failure") is not None) == (check["severity"] == "failure")
        assert (case.find("skipped") is not None) == (check["severity"] == "warning")
    return status


@pytest.mark.parametrize("required_failure", [False, True])
def test_combined_outputs_share_the_exact_decision_and_checks(
    demo_run, tmp_path, capsys, required_failure
):
    spec, run = demo_run
    if required_failure:
        (run / "reports/metrics.json").unlink()
    outputs, options = combined_paths(tmp_path)
    assert main(arguments(spec, run, *options)) == (1 if required_failure else 0)
    assert capsys.readouterr().out == ""
    assert_consistent_outputs(outputs, not required_failure)


def test_json_stdout_can_be_combined_with_markdown_and_junit(demo_run, tmp_path, capsys):
    spec, run = demo_run
    markdown, junit = tmp_path / "packet.md", tmp_path / "junit.xml"
    assert main(arguments(spec, run, "--md-out", str(markdown), "--junit-out", str(junit))) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["recommendation"] == "approved"
    assert "Decision: approved" in markdown.read_text()
    assert ET.parse(junit).getroot().attrib["tests"] == str(status["counts"]["total"])


@pytest.mark.parametrize("strict", [False, True])
def test_optional_warning_policy_is_consistent_across_api_exit_and_all_formats(
    demo_run, tmp_path, strict
):
    spec, run = demo_run
    data = yaml.safe_load(spec.read_text())
    data["reports"].append(
        {"name": "optional-note", "path": "reports/note.json", "required": False}
    )
    spec.write_text(yaml.safe_dump(data))
    outputs, options = combined_paths(tmp_path)
    if strict:
        options.append("--strict-warnings")
    assert main(arguments(spec, run, *options)) == (1 if strict else 0)
    status = assert_consistent_outputs(outputs, not strict)
    assert status["counts"]["warnings"] == (0 if strict else 1)
    assert status["counts"]["failed"] == (1 if strict else 0)
    assert status == validate_run(RunBundle(run), load_spec(spec), strict_warnings=strict).to_dict()


def test_cli_baseline_uses_core_regressions_and_preserves_details(demo_run, tmp_path):
    spec, run = demo_run
    baseline = tmp_path / "baseline"
    shutil.copytree(run, baseline)
    data = yaml.safe_load(spec.read_text())
    data["reports"][0]["regressions"] = {"metrics.accuracy": {"max_decrease": 0.01}}
    spec.write_text(yaml.safe_dump(data))
    report = run / "reports/metrics.json"
    payload = json.loads(report.read_text())
    payload["metrics"]["accuracy"] = 0.90
    report.write_text(json.dumps(payload))
    outputs, options = combined_paths(tmp_path)
    assert main(arguments(spec, run, "--baseline", str(baseline), *options)) == 1
    status = assert_consistent_outputs(outputs, False)
    regression = next(
        check
        for check in status["checks"]
        if check["code"].startswith("regression.") and check["severity"] == "failure"
    )
    assert regression["details"]
    assert "Detail" in outputs[1].read_text()
    xml = ET.parse(outputs[2]).getroot()
    case = next(
        case
        for case in xml.findall("testsuite/testcase")
        if case.find("properties/property[@name='code']").attrib["value"] == regression["code"]
    )
    properties = {
        item.attrib["name"]: item.attrib["value"] for item in case.findall("properties/property")
    }
    assert json.loads(properties["details"]) == regression["details"]
    assert case.attrib["file"] == "reports/metrics.json"


def test_baseline_flag_without_regressions_cannot_suggest_a_comparison(demo_run, tmp_path, capsys):
    spec, run = demo_run
    output = tmp_path / "status.json"
    assert main(arguments(spec, run, "--baseline", str(run), "--json-out", str(output))) == 2
    assert not output.exists()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "requires a contract declaring regressions" in captured.err


@pytest.mark.parametrize(
    "kind",
    [
        "same-output",
        "input-spec",
        "candidate-root",
        "candidate-report",
        "baseline-root",
        "output-symlink",
        "parent-symlink",
        "hardlinked-spec",
        "hardlinked-evidence",
        "hardlinked-outputs",
        "hardlinked-unrelated",
    ],
)
def test_output_alias_preflight_preserves_input_evidence_and_old_outputs(
    demo_run, tmp_path, capsys, kind
):
    spec, run = demo_run
    inputs_before = {
        path: path.read_bytes()
        for path in [spec, run / "reports/metrics.json", run / "artifacts/predictions.csv"]
    }
    first, second = tmp_path / "status.json", tmp_path / "packet.md"
    first.write_bytes(b"previous status")
    second.write_bytes(b"previous packet")
    baseline_option = []
    if kind == "same-output":
        second = first.parent / "." / first.name
    elif kind == "input-spec":
        second = spec
    elif kind == "candidate-root":
        second = run / "packet.md"
    elif kind == "candidate-report":
        second = run / "reports/metrics.json"
    elif kind == "baseline-root":
        baseline = tmp_path / "baseline"
        shutil.copytree(run, baseline)
        second = baseline / "packet.md"
        baseline_option = ["--baseline", str(baseline)]
    elif kind == "output-symlink":
        second.unlink()
        second.symlink_to(spec)
    elif kind == "parent-symlink":
        alias = tmp_path / "alias"
        alias.symlink_to(run, target_is_directory=True)
        second = alias / "packet.md"
    elif kind == "hardlinked-spec":
        second.unlink()
        os.link(spec, second)
    elif kind == "hardlinked-evidence":
        second.unlink()
        os.link(run / "artifacts/predictions.csv", second)
    elif kind == "hardlinked-unrelated":
        unrelated = tmp_path / "unrelated.txt"
        unrelated.write_text("unrelated user data")
        second.unlink()
        os.link(unrelated, second)
    else:
        second.unlink()
        os.link(first, second)
    assert (
        main(
            arguments(
                spec, run, *baseline_option, "--json-out", str(first), "--md-out", str(second)
            )
        )
        == 2
    )
    assert first.read_bytes() == b"previous status"
    assert all(path.read_bytes() == content for path, content in inputs_before.items())
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "no usable result produced" in captured.err
    assert "Traceback" not in captured.err
    assert not list(tmp_path.rglob(".evidence-gate-*"))


def test_output_parents_are_checked_before_any_result_is_written(demo_run, tmp_path):
    spec, run = demo_run
    status = tmp_path / "status.json"
    status.write_text("old approval")
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("occupied")
    assert (
        main(
            arguments(spec, run, "--json-out", str(status), "--md-out", str(blocker / "review.md"))
        )
        == 2
    )
    assert status.read_text() == "old approval"
    assert blocker.read_text() == "occupied"
    assert not list(tmp_path.glob(".evidence-gate-*"))


@pytest.mark.parametrize(
    "names", [("Review.json", "review.json"), ("Café.json", "Cafe\u0301.json")]
)
def test_absent_output_case_and_unicode_aliases_fail_before_publishing(
    demo_run, tmp_path, capsys, names
):
    spec, run = demo_run
    first, second = [tmp_path / name for name in names]
    assert main(arguments(spec, run, "--json-out", str(first), "--md-out", str(second))) == 2
    assert not first.exists()
    assert not second.exists()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "distinct ignoring case and Unicode normalization" in captured.err
    assert not list(tmp_path.glob(".evidence-gate-*"))


@pytest.mark.parametrize("baseline", [False, True])
@pytest.mark.parametrize("unicode_alias", [False, True])
def test_output_run_containment_ignores_case_and_unicode_normalization(
    demo_run, tmp_path, capsys, baseline, unicode_alias
):
    spec, run = demo_run
    protected = tmp_path / ("Café" if unicode_alias else "Candidate")
    shutil.copytree(run, protected)
    alias = protected.with_name("Cafe\u0301" if unicode_alias else "candidate")
    output = alias / "status.json"
    if baseline:
        options = ["--baseline", str(protected)]
    else:
        run, options = protected, []
    assert main(arguments(spec, run, *options, "--json-out", str(output))) == 2
    assert not output.exists()
    assert not (protected / "status.json").exists()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "inside candidate/baseline run roots" in captured.err


@pytest.mark.parametrize("unicode_alias", [False, True])
def test_output_cannot_alias_contract_by_case_or_unicode(demo_run, tmp_path, unicode_alias):
    spec, run = demo_run
    renamed = tmp_path / ("Café.yaml" if unicode_alias else "Contract.yaml")
    shutil.copyfile(spec, renamed)
    output = renamed.with_name("Cafe\u0301.yaml" if unicode_alias else "contract.yaml")
    original = renamed.read_bytes()
    assert main(arguments(renamed, run, "--json-out", str(output))) == 2
    assert renamed.read_bytes() == original


@pytest.mark.parametrize("unicode_alias", [False, True])
def test_packet_input_case_and_unicode_aliases_are_protected(demo_run, tmp_path, unicode_alias):
    spec, run = demo_run
    status = tmp_path / ("Café.json" if unicode_alias else "Status.json")
    original = json.dumps(validate_run(RunBundle(run), load_spec(spec)).to_dict()).encode()
    status.write_bytes(original)
    output = status.with_name("Cafe\u0301.json" if unicode_alias else "status.json")
    assert main(["packet", "--status", str(status), "--md-out", str(output)]) == 2
    assert status.read_bytes() == original


def test_preflight_path_resolution_runtime_error_is_a_controlled_input_error(
    demo_run, tmp_path, monkeypatch, capsys
):
    spec, run = demo_run
    output = tmp_path / "loop.json"
    original = Path.resolve

    def unresolved(path, *args, **kwargs):
        if path == output:
            raise RuntimeError("Symlink loop")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", unresolved)
    assert main(arguments(spec, run, "--json-out", str(output))) == 2
    assert not output.exists()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "could not be resolved; no usable result produced" in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="named pipes require POSIX")
def test_packet_rejects_named_pipe_without_reading_or_publishing(tmp_path, monkeypatch, capsys):
    status = tmp_path / "status.fifo"
    os.mkfifo(status)
    output = tmp_path / "review.md"
    output.write_text("previous packet")
    original_read = Path.read_text

    def unexpected_read(path, *args, **kwargs):
        if path == status:
            raise AssertionError("packet must not read a special file")
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", unexpected_read)
    assert main(["packet", "--status", str(status), "--md-out", str(output)]) == 2
    assert output.read_bytes() == b"previous packet"
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "status input must be an existing regular file" in captured.err
    assert not list(tmp_path.glob(".evidence-gate-*"))


def test_input_error_leaves_previous_outputs_unchanged_and_prints_no_decision(
    demo_run, tmp_path, capsys
):
    spec, run = demo_run
    outputs, options = combined_paths(tmp_path)
    for index, path in enumerate(outputs):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"old result {index}")
    spec.write_text("reports: {}\n")
    assert main(arguments(spec, run, *options)) == 2
    assert [path.read_text() for path in outputs] == [f"old result {index}" for index in range(3)]
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "no usable result produced" in captured.err
    assert not list(outputs[0].parent.glob(".evidence-gate-*"))


@pytest.mark.parametrize("hardlink", [False, True])
def test_packet_cannot_overwrite_its_status_input(demo_run, tmp_path, hardlink):
    spec, run = demo_run
    status = tmp_path / "status.json"
    original = json.dumps(validate_run(RunBundle(run), load_spec(spec)).to_dict()).encode()
    status.write_bytes(original)
    target = status
    if hardlink:
        target = tmp_path / "alias.md"
        os.link(status, target)
    assert main(["packet", "--status", str(status), "--md-out", str(target)]) == 2
    assert status.read_bytes() == original


def hostile_result():
    checks = [
        Check(
            "report.valid",
            "Good <script>alert(1)</script> **approved** ~~ignored~~\x00",
            "pass",
            "<img src=x onerror=alert(1)>",
            "reports/`break`.json",
        ),
        Check(
            "report.optional_missing",
            "Missing | cell\n# forged decision",
            "warning",
            "optional",
            "reports/optional.json",
            {"actual": "<svg onload=alert(1)>|<failure/>", "note": "x" * 1000},
        ),
        Check(
            "baseline.regression",
            'Loss > limit & "quoted"\x01\ud800',
            "failure",
            "evaluation",
            "reports/eval.json",
            {"delta": 0.04},
        ),
    ]
    return ValidationResult(
        False,
        "needs_work",
        checks,
        {"passed": 1, "warnings": 1, "failed": 1, "total": 3},
        "run<script>",
    )


def test_markdown_and_junit_escape_producer_content_and_keep_accurate_counts(tmp_path):
    result = hostile_result()
    markdown = render_review_packet(result)
    assert "<script>" not in markdown
    assert "<img" not in markdown
    assert "<svg" not in markdown
    assert "&lt;script&gt;" in markdown
    assert "\\|" in markdown
    assert "**approved**" not in markdown
    assert "~~ignored~~" not in markdown
    assert "\n# forged decision" not in markdown
    assert "truncated" in markdown
    path = tmp_path / "junit.xml"
    assert write_junit_xml(result, path) == path
    xml = ET.fromstring(render_junit_xml(result))
    assert xml.attrib == {"tests": "3", "failures": "1", "skipped": "1", "errors": "0"}
    cases = xml.findall("testsuite/testcase")
    assert cases[2].find("failure").attrib["message"] == 'Loss > limit & "quoted"\ufffd\ufffd'
    assert len(xml.findall(".//failure")) == 1
    assert len(xml.findall(".//skipped")) == 1
    assert cases[0].attrib["file"] == "reports/`break`.json"
    assert "<svg onload=alert(1)>" in cases[1].find("skipped").text


def test_junit_keeps_checks_with_repeated_codes_and_reports_distinct():
    checks = [
        Check("threshold.valid", "Accuracy meets minimum", "pass", "evaluation"),
        Check("threshold.valid", "Recall meets minimum", "pass", "evaluation"),
    ]
    result = ValidationResult(
        True,
        "approved",
        checks,
        {"passed": 2, "warnings": 0, "failed": 0, "total": 2},
        "run",
    )
    cases = ET.fromstring(render_junit_xml(result)).findall("testsuite/testcase")
    assert len({(case.attrib["classname"], case.attrib["name"]) for case in cases}) == 2
    assert all(
        case.find("properties/property[@name='code']").attrib["value"] == "threshold.valid"
        for case in cases
    )
    assert [case.find("system-out").text for case in cases] == [check.message for check in checks]


@pytest.mark.parametrize("mutation", ["counts", "decision", "severity", "non-finite-details"])
def test_renderers_cannot_bless_a_malformed_programmatic_status(mutation):
    result = hostile_result()
    if mutation == "counts":
        result = replace(result, counts={"passed": 3, "warnings": 0, "failed": 0, "total": 3})
    elif mutation == "decision":
        result = replace(result, passed=True, recommendation="approved")
    elif mutation == "severity":
        result = replace(
            result, checks=[replace(result.checks[0], severity="approved"), *result.checks[1:]]
        )
    else:
        result = replace(
            result,
            checks=[replace(result.checks[0], details={"a": float("nan")}), *result.checks[1:]],
        )
    for renderer in (render_review_packet, render_junit_xml):
        with pytest.raises(ValueError):
            renderer(result)


def test_check_spec_and_metadata_version_are_explicit(tmp_path, capsys, monkeypatch):
    spec = tmp_path / "spec.yaml"
    spec.write_text("reports:\n- name: metrics\n  path: report.json\n")
    assert main(["check-spec", "--spec", str(spec)]) == 0
    assert capsys.readouterr().out == "Contract valid: 1 reports\n"
    spec.write_text("reports: []")
    assert main(["check-spec", "--spec", str(spec)]) == 2
    assert "no usable result produced" in capsys.readouterr().err
    from evidence_gate import cli

    monkeypatch.setattr(cli.metadata, "version", lambda name: "9.8.7")
    with pytest.raises(SystemExit) as version:
        main(["--version"])
    assert version.value.code == 0
    assert capsys.readouterr().out == "evidence-gate 9.8.7\n"


def test_init_example_accepts_named_packaged_study_and_rejects_unknown_name(tmp_path, capsys):
    target = tmp_path / "study"
    assert main(["init-example", str(target), "--name", "model-promotion"]) == 0
    assert (target / "evidence-gate.yaml").is_file()
    assert (target / "run.py").is_file()
    with pytest.raises(SystemExit) as unknown:
        main(["init-example", str(tmp_path / "invalid"), "--name", "missing"])
    assert unknown.value.code == 2
    assert not (tmp_path / "invalid").exists()
    assert "invalid choice" in capsys.readouterr().err


def test_canonical_output_path_does_not_create_dotdot_components_inside_run(demo_run, tmp_path):
    spec, run = demo_run
    output = run / "unneeded" / ".." / ".." / ".." / "ci" / "status.json"
    assert not output.resolve().is_relative_to(run.resolve())
    assert main(arguments(spec, run, "--json-out", str(output))) == 0
    assert not (run / "unneeded").exists()
    assert json.loads(output.resolve().read_text())["passed"] is True


def test_staging_parent_failure_preserves_all_public_outputs(
    demo_run, tmp_path, monkeypatch, capsys
):
    from evidence_gate import cli

    spec, run = demo_run
    outputs, options = combined_paths(tmp_path)
    for path in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("old result")
    original = cli.tempfile.mkstemp
    calls = 0

    def blocked_parent(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise PermissionError("parent unavailable")
        return original(*args, **kwargs)

    monkeypatch.setattr(cli.tempfile, "mkstemp", blocked_parent)
    assert main(arguments(spec, run, *options)) == 2
    assert all(path.read_text() == "old result" for path in outputs)
    assert capsys.readouterr().out == ""
    assert not list(outputs[0].parent.glob(".evidence-gate-*"))


def test_late_publication_error_invalidates_invocation_and_cleans_unpublished_stages(
    demo_run, tmp_path, monkeypatch, capsys
):
    from evidence_gate import cli

    spec, run = demo_run
    outputs, options = combined_paths(tmp_path)
    for path in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("old result")
    original = cli.os.replace
    calls = 0

    def interrupted_batch(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise PermissionError("publication unavailable")
        return original(*args)

    monkeypatch.setattr(cli.os, "replace", interrupted_batch)
    assert main(arguments(spec, run, *options)) == 2
    assert json.loads(outputs[0].read_text())["passed"] is True
    assert outputs[1].read_text() == outputs[2].read_text() == "old result"
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "no usable result produced" in captured.err
    assert not list(outputs[0].parent.glob(".evidence-gate-*"))
