# CLI usage

The `evidence-gate` CLI has three commands:

```text
evidence-gate validate --spec SPEC --run RUN [--json-out STATUS_JSON]
evidence-gate packet --status STATUS_JSON --md-out REVIEW_PACKET_MD
evidence-gate init-example TARGET
```

## validate

Validate a run directory against an evidence contract:

```bash
uv run evidence-gate validate \
  --spec examples/toy-ml-run/evidence-gate.yaml \
  --run examples/toy-ml-run/runs/demo-run \
  --json-out reports/evidence-status.json
```

Arguments:

- `--spec`: YAML or JSON evidence contract.
- `--run`: run directory containing reports and artifacts.
- `--json-out`: optional output path for status JSON. If omitted, JSON is printed to stdout.

Exit behavior:

- `0`: all required checks passed.
- `1`: one or more required checks failed.
- `2`: command-line usage error, unreadable input file, malformed spec, or malformed status JSON. Spec problems are printed to stderr as `spec error: ...` without a Python traceback.

This makes `validate` suitable for CI:

```bash
uv run evidence-gate validate \
  --spec evidence-gate.yaml \
  --run runs/candidate-run \
  --json-out reports/evidence-status.json
```

## packet

Create a Markdown review packet from status JSON:

```bash
uv run evidence-gate packet \
  --status reports/evidence-status.json \
  --md-out reports/review-packet.md
```

`packet` does not re-read the original run reports. It only formats the validation result from the status JSON file. Generate a new status JSON file when the run evidence changes.

## init-example

Copy the bundled synthetic example into a new target directory. This command uses package resources, so it works from a source checkout and from an installed wheel:

```bash
uv run evidence-gate init-example scratch/toy-ml-run
```

The target directory must not already exist. The copied example is local-only and contains synthetic report data.

## Typical local workflow

```bash
# 1. Run your own pipeline, producing reports and artifacts under runs/my-run/.

# 2. Validate the run evidence.
evidence-gate validate \
  --spec evidence-gate.yaml \
  --run runs/my-run \
  --json-out reports/evidence-status.json

# 3. Generate a reviewer-friendly packet.
evidence-gate packet \
  --status reports/evidence-status.json \
  --md-out reports/review-packet.md
```

Keep generated status and packet files wherever your project stores review artifacts. The paths inside them remain relative to the run root.

## CI pattern

This repository includes `.github/workflows/ci.yml` as a complete GitHub Actions example for pytest, ruff, package build, and an Evidence Gate CLI smoke test. For project-specific pipelines, a minimal CI job should install dependencies, run validation, and always upload or print the status JSON when validation fails. Example shell shape:

```bash
set -euo pipefail
mkdir -p reports
if ! evidence-gate validate \
  --spec evidence-gate.yaml \
  --run runs/candidate-run \
  --json-out reports/evidence-status.json; then
  python -m json.tool reports/evidence-status.json
  exit 1
fi

evidence-gate packet \
  --status reports/evidence-status.json \
  --md-out reports/review-packet.md
```

Commit the contract and small synthetic fixtures. Treat generated status files and review packets as build artifacts unless your project intentionally records review decisions in git.
