# First five minutes

This page is the fastest path from a fresh checkout to a validated example run and a review packet you can inspect.

## 1. Install dependencies

```bash
uv sync --dev
```

If you do not have `uv`, install it from the Astral project instructions or use a Python 3.11+ virtual environment with `python -m pip install -e .`.

## 2. Confirm the CLI is available

```bash
uv run evidence-gate --help
```

You should see the three commands: `validate`, `packet`, and `init-example`.

## 3. Validate the bundled toy run

```bash
uv run evidence-gate validate \
  --spec examples/toy-ml-run/evidence-gate.yaml \
  --run examples/toy-ml-run/runs/demo-run \
  --json-out reports/evidence-status.json
```

Expected result:

- exit code `0`;
- `reports/evidence-status.json` exists;
- the JSON has `"passed": true` and `"recommendation": "approved"`.

## 4. Generate the Markdown packet

```bash
uv run evidence-gate packet \
  --status reports/evidence-status.json \
  --md-out reports/review-packet.md
```

Open `reports/review-packet.md`. It should contain:

- the computed decision;
- check counts;
- passed checks;
- any warnings or failures;
- evidence paths relative to the run directory.

## 5. Copy the example and experiment safely

```bash
uv run evidence-gate init-example scratch/my-first-run
uv run evidence-gate validate \
  --spec scratch/my-first-run/evidence-gate.yaml \
  --run scratch/my-first-run/runs/demo-run
```

Try changing `scratch/my-first-run/runs/demo-run/reports/metrics.json` so `accuracy` is below the configured threshold, then validate again. The CLI should exit `1` and report a stable failure code such as `metric.below_min`.

## Troubleshooting

- `target already exists`: `init-example` refuses to overwrite directories. Pick a new target or remove your scratch copy manually.
- `report.missing`: check that the report path in the contract is relative to the `--run` directory.
- `path.absolute` or `path.escape`: replace absolute paths and `..` segments with paths contained by the run directory.
- `table.column_missing`: the referenced CSV exists, but its header is missing a required column.

## What to read next

- `docs/contract-schema.md` for the contract format.
- `docs/cli-usage.md` for exit codes and CI usage.
- `docs/review-packet.md` for status JSON and Markdown packet structure.
- `docs/path-safety.md` before using generated evidence in shared review artifacts.
