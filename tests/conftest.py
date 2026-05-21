from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def demo_run(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / "project"
    run = project / "runs" / "demo-run"
    reports = run / "reports"
    artifacts = run / "artifacts"
    reports.mkdir(parents=True)
    artifacts.mkdir(parents=True)
    (reports / "metrics.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "summary": "Synthetic model evaluation completed.",
                "counts": {"examples": 24, "failures": 0},
                "metrics": {"accuracy": 0.92, "loss": 0.18},
                "outputs": {"predictions": "artifacts/predictions.csv"},
            }
        ),
        encoding="utf-8",
    )
    (artifacts / "predictions.csv").write_text("id,label,score\n1,cat,0.98\n", encoding="utf-8")
    spec = project / "evidence-gate.yaml"
    spec.write_text(
        """
reports:
  - name: metrics
    path: reports/metrics.json
    required: true
    expected_status: passed
    required_fields: [summary]
    counts:
      examples: {min: 1}
      failures: {max: 0}
    metrics:
      accuracy: {min: 0.9}
      loss: {max: 1.0}
    outputs:
      predictions:
        path_field: outputs.predictions
        required: true
        columns: [id, label, score]
""".strip(),
        encoding="utf-8",
    )
    return spec, run
