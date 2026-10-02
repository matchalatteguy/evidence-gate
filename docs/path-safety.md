# Path safety

Evidence Gate treats the run directory as the trust boundary for reports and output artifacts.

## Rule

Every path declared in a contract or report must be:

1. relative, and
2. contained by the run root after resolution.

Valid examples:

```text
reports/metrics.json
artifacts/predictions.csv
nested/reports/quality.json
```

Invalid examples:

```text
ABSOLUTE_PATH/metrics.json
../other-run/metrics.json
artifacts/../../outside.csv
```

## Why this matters

Review packets should be safe to share and easy to reproduce. Absolute paths can leak machine-specific details. Escaping the run root can accidentally validate unrelated files. Evidence Gate rejects both patterns.

## How validation reports path issues

- An absolute artifact path fails with `path.absolute`; an absolute report path uses `path.escape`.
- A path that escapes the run root fails with `path.escape`.
- Missing required reports fail with `report.missing`.
- Missing required artifacts fail with `artifact.missing`.

Rejected path values are redacted as `<outside-run-root>`. Baseline report paths
use the reference's own boundary and fail with `baseline.path_escape`.
Reports and artifacts must be regular files; named pipes cannot wait for a writer
inside validation. Symlink resolution errors fail safely.

CLI review destinations must be outside both run roots and distinct from inputs and
other outputs. Existing symlink/hardlink destinations are refused. This protects
producer evidence from accidental `--json-out` overwrites. The Python producer/file
writer helpers use caller-selected destinations and do not impose this CLI policy.

Destination comparisons conservatively ignore case and canonical Unicode spelling
on every platform. `Review.json`/`review.json` or composed/decomposed accents cannot
be separate outputs, even on a case-sensitive filesystem. This also protects
differently spelled aliases of run roots and input files on macOS.

## Design recommendation

Make each run self-contained:

```text
runs/my-run/
  reports/
    metrics.json
    quality.json
  artifacts/
    predictions.csv
```

Then reference artifacts from reports with relative paths:

```json
{
  "outputs": {
    "predictions": "artifacts/predictions.csv"
  }
}
```

This layout works well in local development, CI workspaces, and archived review bundles.
