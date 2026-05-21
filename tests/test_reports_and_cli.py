from __future__ import annotations

import json
from pathlib import Path

from evidence_gate import RunBundle, load_spec, validate_run, write_review_packet
from evidence_gate.cli import main


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


def test_cli_init_example_copies_bundled_example(tmp_path: Path) -> None:
    target = tmp_path / "copied-example"

    code = main(["init-example", str(target)])

    assert code == 0
    assert (target / "evidence-gate.yaml").is_file()
    assert (target / "runs" / "demo-run" / "reports" / "metrics.json").is_file()
    assert (target / "runs" / "demo-run" / "artifacts" / "predictions.csv").is_file()


def test_bundled_example_validates_successfully() -> None:
    example = Path("examples/toy-ml-run")

    result = validate_run(
        RunBundle(example / "runs" / "demo-run"), load_spec(example / "evidence-gate.yaml")
    )

    assert result.passed is True
    assert result.recommendation == "approved"
