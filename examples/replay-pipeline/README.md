# Review an execution-assumption pipeline

Check that a replay run has valid input ordering, internally consistent comparisons,
and all its promised output files before handing it to a reviewer.

This example connects:

1. **Replay Contract Kit**: check event identities and ordering before simulation.
2. **Replay Realism Kit**: compare named fee, latency, and queue assumptions.
3. **Evidence Gate**: require the resulting report bundle and complete markout evidence.

The thirteen input events describe two invented instruments and multiple price levels.
Three profiles change the simulated fills and costs. All amounts use the same declared
synthetic quote unit; no exchange, external data service, credentials, or live orders are used.
Replay `timestamp` values use milliseconds. The auxiliary ISO-8601 `observed_at` field
expresses those same offsets from a fixed UTC epoch for the dataset contract's timestamp parser.

## Run it

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/). From the repository root:

```bash
cd examples/replay-pipeline
uv run --locked python run.py --output .runs/complete --demonstrate-failure
```

The example's lock file pins the two companion repositories to immutable commits.
The first installation downloads those public sources and dependencies. The pipeline
itself subsequently reads local files and makes no network calls.

Expected result:

```text
Input contract: passed (13 events)
Scenario comparison: 3 profiles; 0 gate failures
Missing export: needs_work; artifact.missing
Complete bundle: approved
Review packet: <output directory>/review.md
```

The missing-export step removes a generated CSV, verifies failure, restores that CSV,
and verifies the same contract again. Each invocation requires a new output directory.
It refuses to overwrite existing results.

## Inspect the evidence

| Output under the run directory | Purpose |
| --- | --- |
| `input/` | Exact local event and scenario inputs used for this run |
| `reports/input-contract.json` | Input validation results and stable failure codes |
| `artifacts/comparison.json` | Profiles, quantities, costs, fill traces, and gate results |
| `artifacts/comparison.csv` | Scenario summary for spreadsheet inspection |
| `artifacts/comparison.md` | Human-readable comparison and model limits |
| `reports/pipeline.json` | Small consumer envelope connecting metrics to output paths |
| `reports/incomplete-status.json` | The deliberate missing-export failure |
| `reports/evidence-status.json` | Final evidence decision |
| `review.md` | Review packet listing each configured check |

The envelope's values are read from the comparison's emitted reports. They are not
hardcoded success labels. It records SHA-256 digests of all four completed exports.
The contract in `evidence.yaml` requires at least three scenarios, zero replay-gate
failures, complete markout coverage among filled decisions, all four declared files,
and matching export bytes. A truncated CSV with its header intact or an emptied
JSON/Markdown/input-contract report fails with `artifact.sha256_mismatch`.

## Deliberately fail each stage

```bash
# Exit 1: duplicate event identity and sequence; replay never runs.
uv run --locked python run.py --output .runs/duplicate --case duplicate-event

# Exit 1: a complete metrics report cannot compensate for an unfinished CSV export.
uv run --locked python run.py --output .runs/missing-export --case missing-export

# Exit 1: input ordering passes, but filled ALPHA decisions lack future markout evidence.
uv run --locked python run.py --output .runs/missing-markout --case missing-markout
```

Output bundles from failed runs remain available for inspection. Exit `2` means that
the command could not process its inputs or create its output directory.

## Adapt the workflow

- Map your event fields in `manifest.json`; keep input validation before simulation.
- Describe explicit assumptions in `scenarios.yaml`. The `reference` profile is a
  comparison baseline, not a selected profitable strategy.
- Change evidence requirements in `evidence.yaml` to match the outputs you promise.
- Preserve both failed and completed run directories so a reviewer can reproduce them.

This consumer is an example, not a new orchestration framework. Its Python subprocess
executes the installed replay CLI with explicit arguments and inspects the actual files.

## Verify the example

```bash
uv sync --locked --group dev
uv run --locked pytest -q test_pipeline.py
```

Tests exercise the complete run, missing export, duplicate inputs, missing future evidence,
truncated/tampered exports, and refusal to overwrite earlier results. The repository's CI runs this example separately
from the standalone evidence checker, preserving its small dependency surface.

## What approval establishes

Approval establishes that this fixture's configured input and output checks passed.
Matching hashes establish byte integrity against the producer's envelope; they trust
that envelope and do not authenticate sources or validate artifact content/schema.
It does not authenticate source prices, establish statistical adequacy, validate venue
matching behavior, or demonstrate trading profitability. Execution decisions remain
independent, and the synthetic scenarios do not describe observed market conditions.
