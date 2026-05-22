# Evidence Gate

Evidence Gate is a local-first Python library and CLI for deciding whether a run directory contains enough machine-checkable evidence for review. It is useful for research, evaluation, benchmark, document-processing, and data-build pipelines where results should not move forward until required reports and artifacts are present, well shaped, and easy for a reviewer to inspect.

Use it when a pipeline writes files like this:

```text
runs/demo-run/
  reports/metrics.json
  artifacts/predictions.csv
```

…and you want one command to answer:

- Did every required report get written?
- Do reports have the expected status and required fields?
- Are counts and metrics finite and inside configured thresholds?
- Do declared output artifacts exist?
- Do artifact paths stay inside the run directory?
- Do lightweight CSV artifacts contain expected columns?
- Can the run produce a JSON status file and Markdown review packet for CI or human review?

Evidence Gate is intentionally offline. It validates local files only. It does not call hosted services, manage credentials, upload artifacts, or run live integrations.

## Install

From a local checkout:

```bash
uv sync --dev
uv run evidence-gate --help
```

Or install with pip from a source checkout:

```bash
python -m pip install .
evidence-gate --help
```

## Quickstart

For a complete walkthrough, start with `docs/first-five-minutes.md`. The shortest path is:

```bash
uv sync --dev
uv run evidence-gate validate \
  --spec examples/toy-ml-run/evidence-gate.yaml \
  --run examples/toy-ml-run/runs/demo-run \
  --json-out reports/evidence-status.json
uv run evidence-gate packet \
  --status reports/evidence-status.json \
  --md-out reports/review-packet.md
```

The `validate` command exits with status `0` when required checks pass and `1` when required checks fail. The JSON output is suitable for CI logs or downstream tools. The Markdown packet is intended for a reviewer, release checklist, or local decision note.

## Should you use Evidence Gate?

Use Evidence Gate when you need a small, local, inspectable gate for file-producing pipelines:

- benchmark or evaluation runs that emit JSON metrics and CSV summaries;
- data-build jobs that must prove row counts, failure counts, and output artifacts;
- document/OCR pipelines that need a reviewer packet before results move forward;
- agent workflows where stable failure codes are easier to remediate than prose logs.

Do not use it as an experiment tracker, dashboard, scheduler, artifact store, or general schema-validation framework. The current schema is intentionally narrow: JSON report objects, relative local artifacts, finite numeric thresholds, and CSV header checks. If you need hosted state, authentication, remote mutation, large dataset validation, or custom plugin execution, keep Evidence Gate as a lightweight final readiness check rather than the system of record.

To copy a fresh synthetic example into another directory (available from source checkouts and installed packages):

```bash
uv run evidence-gate init-example scratch/toy-run
```

Then validate the copied run:

```bash
uv run evidence-gate validate \
  --spec scratch/toy-run/evidence-gate.yaml \
  --run scratch/toy-run/runs/demo-run
```

## Evidence contract in one screen

A contract is a YAML file that says which reports and artifacts must exist under a run directory:

```yaml
schema_version: 1
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
    numeric:
      diagnostics.sample_count: {min: 1}
    outputs:
      predictions:
        path_field: outputs.predictions
        required: true
        csv_columns: [id, label, score]
```

The corresponding report can be any JSON object with the fields referenced by the contract:

```json
{
  "status": "passed",
  "summary": "Synthetic classifier evaluation completed.",
  "counts": {"examples": 24, "failures": 0},
  "metrics": {"accuracy": 0.96, "loss": 0.18},
  "outputs": {"predictions": "artifacts/predictions.csv"}
}
```

All paths are relative to the run root. Absolute paths and `..` escapes fail validation.

## Python API

```python
from pathlib import Path

from evidence_gate import RunBundle, load_spec, render_review_packet, validate_run

spec = load_spec(Path("examples/toy-ml-run/evidence-gate.yaml"))
bundle = RunBundle(Path("examples/toy-ml-run/runs/demo-run"))
result = validate_run(bundle, spec)

if not result.passed:
    for failure in result.failures:
        print(f"{failure.code}: {failure.message}")

print(render_review_packet(result))
```

## Documentation map

- `docs/first-five-minutes.md` - fastest setup, validation, packet generation, and troubleshooting path.
- `docs/contract-schema.md` - full contract reference and example JSON report.
- `docs/cli-usage.md` - command reference, exit behavior, and CI pattern.
- `docs/python-api.md` - API-oriented usage notes for agents and engineers.
- `docs/llm-agent-guide.md` - safe agent workflow and failure-code remediation map.
- `docs/review-packet.md` - generated JSON status and Markdown packet structure.
- `docs/path-safety.md` - how relative path containment works.
- `docs/non-goals.md` - boundaries and intentionally unsupported features.
- `examples/toy-ml-run/README.md` - synthetic example layout and adaptation notes.

## Development

```bash
uv sync --dev
uv run pytest
uv run ruff check .
```

## Non-goals

Evidence Gate is not an experiment tracker, hosted dashboard, data lake, scheduler, model registry, artifact store, or networked service. It does not authenticate to external systems, start jobs, mutate remote state, or replace human review. It only validates local evidence files and writes local review artifacts.

## Project status

This is a small MVP intended to be easy to inspect, extend, and use from local scripts or CI. The public API is intentionally compact: load a spec, create a run bundle, validate it, and write review artifacts.

## License

MIT
