from __future__ import annotations

import json
from pathlib import Path

from evidence_gate.models import ValidationResult


def write_status_json(result: ValidationResult, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def write_review_packet(result: ValidationResult, output_dir: Path, markdown: bool = True) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / ("review-packet.md" if markdown else "review-packet.json")
    if markdown:
        path.write_text(to_markdown(result), encoding="utf-8")
    else:
        path.write_text(json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def to_markdown(result: ValidationResult) -> str:
    lines = [
        "# Evidence Review Packet",
        "",
        f"Decision: {result.recommendation}",
        "",
        "## Counts",
        "",
    ]
    for key in ("passed", "warnings", "failed", "total"):
        lines.append(f"- {key}: {result.counts.get(key, 0)}")
    lines.extend(["", "## Checks", ""])
    for check in result.checks:
        path = f" (`{check.path}`)" if check.path else ""
        report = f" [{check.report}]" if check.report else ""
        lines.append(f"- **{check.severity}** `{check.code}`{report}{path}: {check.message}")
    return "\n".join(lines) + "\n"
