# CLI usage

The `evidence-gate` CLI provides these commands:

```text
evidence-gate validate --spec SPEC --run RUN [--baseline REFERENCE] [--strict-warnings] [--json-out STATUS_JSON] [--md-out REVIEW_MD] [--junit-out JUNIT_XML]
evidence-gate check-spec --spec SPEC
evidence-gate packet --status STATUS_JSON --md-out REVIEW_PACKET_MD
evidence-gate init-example TARGET [--name toy-ml-run|model-promotion]
evidence-gate --version
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
- `--md-out`, `--junit-out`: write the same result as Markdown and JUnit XML in this invocation, including when evidence fails.
- `--baseline`: reference run root for explicitly configured `regressions`; both roots must exist and differ.
- `--strict-warnings`: promote optional missing evidence warnings to failures consistently in the API result and all outputs.

Outputs must be distinct and outside candidate/reference roots, and cannot replace the
contract or other input files. Existing symlink/hardlink output destinations are refused.
Path comparisons ignore case and canonical Unicode spelling on all platforms;
choose filenames that remain distinct under that conservative policy.
Each output uses same-directory staging and atomic replacement. Multiple files are
not a filesystem transaction: a late replacement error can leave a mixture of old/new
files. On exit `2`, treat every output as unusable for this invocation. Input/preflight
errors preserve earlier outputs; they are not a new approval. See the [CI recipe](ci-integration.md).

Exit behavior:

- `0`: all required checks passed.
- `1`: one or more required checks failed.
- `2`: command-line usage error, unreadable input file, malformed spec, or malformed status JSON. Spec problems are printed to stderr as `spec error: ...` without a Python traceback.

Exit `2` also covers missing run directories or output-destination errors. No usable
validation decision is produced; ignore previous status/packet files.

## check-spec

`evidence-gate check-spec --spec contract.yaml` checks contract structure without
reading run evidence and prints the report count on success. It catches unknown
keys, malformed types, duplicate fields, and contradictory limits. This is not a
dry run of file existence, permissions, or the producer's correctness.

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

The target directory must not already exist. The default example is `toy-ml-run`;
`--name model-promotion` copies the executable baseline/content-check example.
Examples are local-only and use synthetic data. Python scripts require the environment
where the library is installed; an isolated `uv tool` CLI alone does not install it
into your system Python. See the [installed example recipe](../examples/model-promotion/README.md).

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

This repository includes `.github/workflows/ci.yml` for tests, lint, builds, and
installed-package examples. The [CI integration recipe](ci-integration.md) writes
all report formats in one invocation and preserves exit `1` failures. A minimal
JSON-only shell pattern preserves the gate exit and avoids old status files on exit `2`:

```bash
set -euo pipefail
mkdir -p reports
if evidence-gate validate \
  --spec evidence-gate.yaml \
  --run runs/candidate-run \
  --json-out reports/evidence-status.json; then
  gate_exit=0
else
  gate_exit=$?
fi
if [ "$gate_exit" -eq 2 ]; then
  exit 2
fi
evidence-gate packet \
  --status reports/evidence-status.json \
  --md-out reports/review-packet.md
exit "$gate_exit"
```

Commit the contract and small synthetic fixtures. Treat generated status files and review packets as build artifacts unless your project intentionally records review decisions in git.
