# Evidence Gate

[![Checks](https://github.com/matchalatteguy/evidence-gate/actions/workflows/ci.yml/badge.svg)](https://github.com/matchalatteguy/evidence-gate/actions/workflows/ci.yml)

**Stop incomplete exports and metric regressions before promoting a pipeline run.**

Evidence Gate is a small Python library and CLI for pipelines that write JSON reports
and local artifacts. A YAML contract checks the actual files, CSV contents, numeric
limits, and changes against a reference run. One command produces a consistent exit
code, JSON decision, Markdown review, and JUnit XML.

A report can say `"status": "passed"` while its CSV is truncated or its accuracy has
dropped. This gate checks those promises before the run reaches review or release.

## See three failures, then a successful promotion

Python 3.11 or newer. From a checkout:

```bash
uv sync --locked --dev
uv run python examples/model-promotion/run.py --output .runs/promotion --demonstrate-failure
```

The [runnable example](examples/model-promotion/README.md) evaluates a keyword classifier
on 100 synthetic support messages and compares it with a previous run on the same dataset:

```text
regression: accuracy=0.80; needs_work; regression.decrease
truncated: accuracy=1.00; needs_work; table.row_count_below_min, table.row_count_mismatch
nonfinite: accuracy=1.00; needs_work; table.invalid_number
improved: accuracy=1.00; approved
```

All four candidates meet the fixed accuracy floor. All exports have correct producer
hashes. The baseline and content checks explain why only the last run is promotable.
JSON, Markdown, and JUnit results are saved under `.runs/promotion/reviews/`.

The data is invented; predictions and accuracy are computed by the example.
This demonstrates the gate, not the quality of a production classifier.

## Install and run

```bash
uv tool install 'git+https://github.com/matchalatteguy/evidence-gate.git@v0.4.0'
evidence-gate --version
evidence-gate init-example scratch/toy-run
evidence-gate check-spec --spec scratch/toy-run/evidence-gate.yaml
evidence-gate validate --spec scratch/toy-run/evidence-gate.yaml --run scratch/toy-run/runs/demo-run --json-out review/status.json --md-out review/summary.md --junit-out review/junit.xml
```

For Python scripts, install in your project's environment with
`pip install 'git+https://github.com/matchalatteguy/evidence-gate.git@v0.4.0'`.
The [release](https://github.com/matchalatteguy/evidence-gate/releases/tag/v0.4.0)
also supplies a wheel and source archive. Runtime dependency: PyYAML.

| Exit | Meaning |
| --- | --- |
| `0` | The configured evidence checks passed. Optional missing evidence may warn. |
| `1` | Evidence failed its contract; JSON, Markdown, and JUnit contain the failures. |
| `2` | Contract, inputs, or output destinations could not be processed. No usable new validation decision is produced. |

Use `--strict-warnings` when optional missing evidence should block promotion.
Write review outputs outside candidate and reference directories; aliases are refused
to protect evidence files. On exit `2`, ignore any earlier output files.

## A contract for CSV content and metric changes

```yaml
schema_version: 1
reports:
  - name: evaluation
    path: reports/evaluation.json
    expected_status: passed
    counts:
      examples: {min: 100}
    metrics:
      accuracy: {min: 0.75, max: 1}
    baseline_match_fields: [dataset_sha256]
    regressions:
      metrics.accuracy: {max_decrease: 0.02}
      metrics.latency_ms: {max_increase: 5}
    outputs:
      predictions:
        path_field: outputs.predictions
        sha256_field: sha256.predictions
        csv:
          rows: {min: 100}
          row_count_field: counts.examples
          columns:
            id: {type: integer, min: 0}
            label: {type: string}
            score: {type: number, min: 0, max: 1}
```

The producer report contains those fields and relative output paths. Regression
limits use original units: `0.02` is two percentage points for an accuracy fraction;
`5` is five milliseconds for `latency_ms`.

```bash
evidence-gate validate --spec evidence-gate.yaml --run runs/candidate --baseline runs/reference --json-out review/status.json --md-out review/summary.md --junit-out review/junit.xml
```

Missing or invalid comparison values fail. `baseline_match_fields` prevents comparing
reports with different declared datasets or configurations. Each reference report uses
the candidate's relative report path. [Complete contract reference](docs/contract-schema.md).

## What you can check

| Need | Contract or command |
| --- | --- |
| Missing report/export, wrong completion status | `reports`, `expected_status`, `outputs` |
| Absolute metric limits or integer counts | `metrics`, `numeric`, `counts` |
| Regressions from a reference | `regressions`, `baseline_match_fields`, `--baseline` |
| Header-only, truncated, or malformed CSV | `csv.rows`, `csv.row_count_field`, full row parsing |
| Empty, nonfinite, mistyped, or out-of-range cells | `csv.columns` |
| Output bytes changed after completion | `sha256_field` |
| Machine-readable failures and a readable review | `--json-out`, `--md-out`, `--junit-out` |
| Contract mistakes before the expensive run | `check-spec` |

CSV checks stream records with bounded error samples. Duplicate/blank headers,
inconsistent row widths, and malformed CSV fail. The legacy `csv_columns` option
continues to check headers only.

## Python producer and validator API

```python
from pathlib import Path
from evidence_gate import (
    RunBundle, load_spec, output_sha256, validate_run, write_report_atomic,
)

# Close the export before recording its fingerprint and completed report.
report["sha256"] = {"predictions": output_sha256(run_root / "artifacts/predictions.csv")}
write_report_atomic(run_root / "reports/evaluation.json", report)

result = validate_run(
    RunBundle(Path("runs/candidate")), load_spec(Path("evidence-gate.yaml")),
    baseline=RunBundle(Path("runs/reference")), strict_warnings=True,
)
for failure in result.failures:
    print(failure.code, failure.message, failure.details)
```

These fragments belong inside your producer; `report` and `run_root` are its values.
[Python API](docs/python-api.md) · [Producer recipe](docs/producer-guide.md).

## Use in CI

Feed JUnit to your test reporter and Markdown to the GitHub Actions job summary.
The [copyable CI recipe](docs/ci-integration.md) preserves failure reports and stops
promotion on exit `1` or `2`.

More runnable examples:

- [Missing export → completed export](examples/missing_export.py).
- [Pinned input-contract → replay → evidence review](examples/replay-pipeline/README.md).
- [Model change → regression/content failure → successful promotion](examples/model-promotion/README.md).

## Scope and trust

`approved` means the **configured** checks passed. The producer supplies metrics,
dataset identities, and expected hashes; the gate does not independently establish
their truth or recompute accuracy. A reference is a comparison input, not proof that a
previous run was approved. Choose it deliberately and preserve its evidence.

The tool checks local files, finite numbers, CSV record structure/types/ranges, and
declared comparisons. It does not execute pipeline code, validate arbitrary JSON
Schemas, check CSV key uniqueness, or provide a scheduler, hosted state, or scientific
review. Writers must finish before validation. Path containment protects trusted local
workflows; it is not a sandbox against hostile concurrent file changes.

[Path safety](docs/path-safety.md) · [Failure codes](docs/failure-codes.md) ·
[Migration notes](CHANGELOG.md) · [First five minutes](docs/first-five-minutes.md) ·
[MIT license](LICENSE).

## Development

```bash
uv sync --locked --dev
uv run pytest -W error::DeprecationWarning
uv run ruff check .
uv run ruff format --check .
uv build
```

CI runs on Python 3.11–3.14, tests intentional failures, and installs the wheel outside
the checkout to execute both bundled examples. Replay integration separately uses
locked companion commits.
