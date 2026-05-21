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

- A report or artifact path that is absolute fails with `path.absolute`.
- A path that escapes the run root fails with `path.escape`.
- Missing required reports fail with `report.missing`.
- Missing required artifacts fail with `artifact.missing`.

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
