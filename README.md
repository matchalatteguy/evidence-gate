# Evidence Gate

Evidence Gate is a small local-first Python library and CLI for checking whether a research,
evaluation, benchmark, or data-processing run has enough machine-checkable evidence for review.

It answers practical questions before a human review:

- Did every required report get written?
- Do reports have the expected status and required fields?
- Are counts and metrics valid and within thresholds?
- Do declared output artifacts stay inside the run directory?
- Do lightweight CSV artifacts contain the expected columns?
- Can the run produce a JSON status file and Markdown review packet?

Evidence Gate is intentionally offline. It does not call hosted services, manage credentials, or run
live integrations.

## Install

From a local checkout:

```bash
uv sync --dev
uv run evidence-gate --help
```

Or install with pip from a source checkout:

```bash
python -m pip install .
```

## Quickstart

Validate the synthetic example run:

```bash
uv run evidence-gate validate \
  --spec examples/toy-ml-run/evidence-gate.yaml \
  --run examples/toy-ml-run/runs/demo-run \
  --json-out reports/evidence-status.json

uv run evidence-gate packet \
  --status reports/evidence-status.json \
  --md-out reports/review-packet.md
```

The first command exits with status `0` when required checks pass and `1` when required checks fail.
The JSON output is suitable for CI logs or downstream tools. The Markdown packet is intended for a
human reviewer.

## Python API

```python
from pathlib import Path

from evidence_gate import RunBundle, load_spec, validate_run, write_review_packet

spec = load_spec(Path("examples/toy-ml-run/evidence-gate.yaml"))
result = validate_run(RunBundle(Path("examples/toy-ml-run/runs/demo-run")), spec)
write_review_packet(result, Path("reports"), markdown=True)
```

## Evidence spec shape

```yaml
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
    outputs:
      predictions:
        path_field: outputs.predictions
        required: true
        columns: [id, label, score]
```

See `docs/contract-schema.md` and `docs/review-packet.md` for details.

## Non-goals

Evidence Gate is not an experiment tracker, hosted dashboard, data lake, scheduler, or networked
service. It validates local files and emits review artifacts.

## Development

```bash
uv sync --dev
uv run pytest
uv run ruff check .
```

## License

MIT
