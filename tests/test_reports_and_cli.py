from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from evidence_gate import (
    RunBundle,
    load_spec,
    render_review_packet,
    validate_run,
    write_review_packet,
    write_review_packet_file,
)
from evidence_gate.cli import SPEC_ERROR_EXIT_CODE, main


def test_markdown_packet_contains_decision_checks_and_links(
    demo_run: tuple[Path, Path], tmp_path: Path
) -> None:
    spec_path, run_path = demo_run
    result = validate_run(RunBundle(run_path), load_spec(spec_path))

    packet_path = write_review_packet(result, tmp_path, markdown=True)

    text = packet_path.read_text(encoding="utf-8")
    assert "# Evidence Review Packet" in text
    assert "Decision: approved" in text
    assert "report.valid" in text
    assert "reports/metrics.json" in text


def test_render_and_explicit_packet_file_api_match(
    demo_run: tuple[Path, Path], tmp_path: Path
) -> None:
    spec_path, run_path = demo_run
    result = validate_run(RunBundle(run_path), load_spec(spec_path))
    packet_path = tmp_path / "nested" / "custom-packet.md"

    written_path = write_review_packet_file(result, packet_path)

    assert written_path == packet_path
    assert packet_path.read_text(encoding="utf-8") == render_review_packet(result)


def test_cli_validate_writes_json_and_returns_zero(
    demo_run: tuple[Path, Path], tmp_path: Path
) -> None:
    spec_path, run_path = demo_run
    status_path = tmp_path / "evidence-status.json"

    code = main(
        [
            "validate",
            "--spec",
            str(spec_path),
            "--run",
            str(run_path),
            "--json-out",
            str(status_path),
        ]
    )

    assert code == 0
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["passed"] is True
    assert payload["recommendation"] == "approved"


def test_cli_validate_returns_nonzero_on_required_failure(
    demo_run: tuple[Path, Path], tmp_path: Path
) -> None:
    spec_path, run_path = demo_run
    (run_path / "reports" / "metrics.json").unlink()

    code = main(["validate", "--spec", str(spec_path), "--run", str(run_path)])

    assert code == 1


def test_cli_packet_writes_markdown_from_status_json(
    demo_run: tuple[Path, Path], tmp_path: Path
) -> None:
    spec_path, run_path = demo_run
    status_path = tmp_path / "status.json"
    md_path = tmp_path / "review-packet.md"
    result = validate_run(RunBundle(run_path), load_spec(spec_path))
    status_path.write_text(json.dumps(result.to_dict()), encoding="utf-8")

    code = main(["packet", "--status", str(status_path), "--md-out", str(md_path)])

    assert code == 0
    assert "Decision: approved" in md_path.read_text(encoding="utf-8")


def test_explicit_packet_writer_uses_requested_file_without_intermediate_coupling(
    demo_run: tuple[Path, Path], tmp_path: Path
) -> None:
    spec_path, run_path = demo_run
    result = validate_run(RunBundle(run_path), load_spec(spec_path))
    md_path = tmp_path / "nested" / "custom-review-name.md"

    written = write_review_packet_file(result, md_path)

    assert written == md_path
    assert "Schema version: 1" in md_path.read_text(encoding="utf-8")
    assert not (md_path.parent / "review-packet.md").exists()


def test_render_review_packet_is_pure_markdown_api(demo_run: tuple[Path, Path]) -> None:
    spec_path, run_path = demo_run
    result = validate_run(RunBundle(run_path), load_spec(spec_path))

    text = render_review_packet(result)

    assert text.startswith("# Evidence Review Packet\n")
    assert "Decision: approved" in text


def test_cli_packet_reports_malformed_status_json_without_traceback(tmp_path: Path, capsys) -> None:
    status_path = tmp_path / "status.json"
    md_path = tmp_path / "review-packet.md"
    status_path.write_text("{not json}\n", encoding="utf-8")

    code = main(["packet", "--status", str(status_path), "--md-out", str(md_path)])

    captured = capsys.readouterr()
    assert code == SPEC_ERROR_EXIT_CODE
    assert "input error:" in captured.err
    assert "Traceback" not in captured.err


def test_cli_packet_reports_malformed_status_shape_without_traceback(
    tmp_path: Path, capsys
) -> None:
    status_path = tmp_path / "status.json"
    md_path = tmp_path / "review-packet.md"
    status_path.write_text("{}\n", encoding="utf-8")

    code = main(["packet", "--status", str(status_path), "--md-out", str(md_path)])

    captured = capsys.readouterr()
    assert code == SPEC_ERROR_EXIT_CODE
    assert "input error:" in captured.err
    assert "Traceback" not in captured.err


def test_subprocess_cli_validate_exit_codes_and_streams(
    demo_run: tuple[Path, Path], tmp_path: Path
) -> None:
    spec_path, run_path = demo_run
    status_path = tmp_path / "status.json"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "evidence_gate.cli",
            "validate",
            "--spec",
            str(spec_path),
            "--run",
            str(run_path),
            "--json-out",
            str(status_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    assert json.loads(status_path.read_text(encoding="utf-8"))["passed"] is True


def test_cli_validate_reports_spec_errors_without_traceback(
    demo_run: tuple[Path, Path], capsys
) -> None:
    spec_path, run_path = demo_run
    spec_path.write_text("reports: {}\n", encoding="utf-8")

    code = main(["validate", "--spec", str(spec_path), "--run", str(run_path)])

    captured = capsys.readouterr()
    assert code == SPEC_ERROR_EXIT_CODE
    assert "spec error:" in captured.err
    assert "Traceback" not in captured.err


def test_cli_init_example_copies_bundled_example(tmp_path: Path) -> None:
    target = tmp_path / "copied-example"

    code = main(["init-example", str(target)])

    assert code == 0
    assert (target / "evidence-gate.yaml").is_file()
    assert (target / "runs" / "demo-run" / "reports" / "metrics.json").is_file()
    assert (target / "runs" / "demo-run" / "artifacts" / "predictions.csv").is_file()


def test_cli_init_example_refuses_existing_target_without_traceback(tmp_path: Path, capsys) -> None:
    target = tmp_path / "copied-example"
    target.mkdir()

    code = main(["init-example", str(target)])

    captured = capsys.readouterr()
    assert code == SPEC_ERROR_EXIT_CODE
    assert f"target already exists: {target}" in captured.err
    assert "Traceback" not in captured.err


def test_bundled_example_validates_successfully() -> None:
    example = Path("examples/toy-ml-run")

    result = validate_run(
        RunBundle(example / "runs" / "demo-run"), load_spec(example / "evidence-gate.yaml")
    )

    assert result.passed is True
    assert result.recommendation == "approved"


def test_subprocess_cli_validate_success_outputs_json(demo_run: tuple[Path, Path]) -> None:
    spec_path, run_path = demo_run

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "evidence_gate.cli",
            "validate",
            "--spec",
            str(spec_path),
            "--run",
            str(run_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    payload = json.loads(completed.stdout)
    assert payload["passed"] is True
    assert payload["recommendation"] == "approved"


def test_subprocess_cli_validate_required_failure_exits_one(demo_run: tuple[Path, Path]) -> None:
    spec_path, run_path = demo_run
    (run_path / "reports" / "metrics.json").unlink()

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "evidence_gate.cli",
            "validate",
            "--spec",
            str(spec_path),
            "--run",
            str(run_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert completed.stderr == ""
    payload = json.loads(completed.stdout)
    assert payload["passed"] is False
    assert any(check["code"] == "report.missing" for check in payload["checks"])
