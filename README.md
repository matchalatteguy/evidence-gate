# Evidence Gate

[![Checks](https://github.com/matchalatteguy/evidence-gate/actions/workflows/ci.yml/badge.svg)](https://github.com/matchalatteguy/evidence-gate/actions/workflows/ci.yml)

A Python library and CLI that checks whether a file-producing pipeline has delivered its promised evidence. Give it a run directory and a YAML contract; it returns a pass/fail decision, stable failure codes, and a Markdown review packet.

A metrics report can say `"status": "passed"` even when its predictions export never finished. Evidence Gate catches that gap before the run moves to review or release.

## Try a failure, then fix it

Python 3.11 or newer. From a checkout:

```bash
uv sync --locked --dev
uv run python examples/missing_export.py
```

The runnable [demo](examples/missing_export.py) removes the CSV export from the bundled example, runs the CLI, finishes the export, then runs the same contract again. It uses a temporary directory and leaves the example unchanged:

```text
Before export: exit 1; artifact.missing
After export:  exit 0; approved (10 checks)
```

The example data and metrics are synthetic; the demonstration is of the gate's behavior.

## Review a complete replay pipeline

The [replay review example](examples/replay-pipeline/README.md) connects three tools:
input ordering and identity checks, execution-assumption comparisons, and this evidence gate.
It runs three profiles over two instruments with multiple book levels, produces JSON/CSV/Markdown
artifacts, then demonstrates a missing export that blocks review despite passing metrics.
The example pins its companion tools and checks the actual emitted reports.

```bash
cd examples/replay-pipeline
uv run --locked python run.py --output .runs/complete --demonstrate-failure
```

Separate failure cases show duplicate inputs stopping before simulation and missing future
evidence preventing promotion. The prices and decisions are synthetic; this is a pipeline
verification example, not a strategy-performance estimate.

## Use it in your pipeline

```bash
# Install the versioned CLI. From a checkout, uv run or pip install . also works.
uv tool install 'git+https://github.com/matchalatteguy/evidence-gate.git@v0.3.0'
evidence-gate init-example scratch/toy-run

evidence-gate validate \
  --spec scratch/toy-run/evidence-gate.yaml \
  --run scratch/toy-run/runs/demo-run \
  --json-out scratch/status.json

evidence-gate packet \
  --status scratch/status.json \
  --md-out scratch/review-packet.md
```

| Exit | Meaning |
|---|---|
| `0` | Required checks passed; missing optional evidence can produce warnings. |
| `1` | The run failed its evidence contract. |
| `2` | The contract, command inputs, or requested output files could not be processed. |

Without `--json-out`, validation prints JSON to stdout. Errors go to stderr. A pipeline can use exit `1` to stop promotion and the failure codes to identify what needs repair.

## A small contract

```yaml
schema_version: 1
reports:
  - name: evaluation
    path: reports/metrics.json
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
        csv_columns: [id, label, score]
```

The report is a JSON object containing the named `status`, `summary`, `counts`, `metrics`, and `outputs` fields. Output paths are relative to the run root. Contracts reject empty report lists, unknown fields, and contradictory thresholds; paths that escape the run root, including escaping symlinks, fail validation.

## Detect changed or truncated exports

Optionally bind an output to the SHA-256 digest recorded in its producer's report:

```yaml
outputs:
  predictions:
    path_field: outputs.predictions
    sha256_field: sha256.predictions
```

After finishing the export, the producer writes its 64-hex digest at `sha256.predictions` in the report. Validation hashes the artifact in chunks and fails for missing/malformed digests, changed bytes, or read errors. The [replay example](examples/replay-pipeline/README.md) applies this to all four exports, so a header-only CSV or emptied report cannot retain approval. [Digest contract details](docs/contract-schema.md#output-byte-integrity).

## Python API

```python
from pathlib import Path
from evidence_gate import RunBundle, load_spec, validate_run

result = validate_run(RunBundle(Path("runs/demo")), load_spec(Path("contract.yaml")))
for failure in result.failures:
    print(f"{failure.code}: {failure.message}")
```

## What the decision means

`approved` means the configured file and value checks passed. It does not verify that a report is truthful, that an experiment is sound, or that a model is useful. CSV checks inspect headers, not rows. A matching digest establishes byte integrity against the trusted producer's report; it does not authenticate sources or validate artifact content/schema. Contracts and files should come from trusted local pipelines; containment checks are not a sandbox for hostile processes changing files during validation.

The tool supports JSON reports, finite numeric thresholds, local file artifacts, optional SHA-256 integrity checks, and CSV headers. It has no scheduler, hosted state, network calls, or plugin execution. Version 0.3 adds opt-in artifact digests while preserving unconfigured contracts; see the [migration notes](CHANGELOG.md).

## Documentation and development

[First five minutes](docs/first-five-minutes.md) · [Contract schema](docs/contract-schema.md) · [CLI and CI usage](docs/cli-usage.md) · [Python API](docs/python-api.md) · [Review packets](docs/review-packet.md) · [Path safety](docs/path-safety.md)

```bash
uv sync --locked --dev
uv run pytest -W error::DeprecationWarning
uv run ruff check .
uv run ruff format --check .
uv build
```

CI runs those checks on Python 3.11–3.14, executes the failure-to-pass demo, and installs the built wheel outside the checkout to verify its bundled example and CLI.

[MIT license](LICENSE).
