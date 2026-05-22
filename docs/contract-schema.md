# Contract schema

An Evidence Gate contract declares the reports that should exist inside a run directory and the checks that make those reports review-ready. Contracts are YAML or JSON files loaded with `load_spec()` or passed to `evidence-gate validate --spec`.

## Top-level shape

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
    numeric:
      diagnostics.sample_count: {min: 1}
    outputs:
      predictions:
        path_field: outputs.predictions
        required: true
        csv_columns: [id, label, score]
```

## Top-level fields

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `schema_version` | integer | no, defaults to `1` | Contract schema version. Version `1` is currently supported; unsupported versions fail during spec loading. |
| `reports` | list of report specifications | yes | Reports to validate under the run root. |

The initial schema is deliberately small. If your pipeline has many stages, model each stage as one report specification with stable field names.

## Report specification

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `name` | string | yes | Stable report name used in check messages. |
| `path` | string | yes | Relative path from run root to a JSON report. |
| `required` | boolean | no, defaults true | Missing required reports fail validation; missing optional reports warn. |
| `expected_status` | string or null | no | Expected value of the report object's `status` field. |
| `required_fields` | list of dot paths | no | Fields that must exist in the report object. |
| `counts` | map of threshold specs | no | Numeric count values to check under report field `counts`. |
| `metrics` | map of threshold specs | no | Numeric metric values to check under report field `metrics`. |
| `numeric` | map of dot path to threshold spec | no | Finite numeric values anywhere in the report object, addressed by dot path. |
| `outputs` | map of output specs | no | Artifacts declared by fields in the report object. |

Report files must contain JSON objects. Arrays, strings, and malformed JSON fail with `report.invalid_json`.

## Dot paths

`required_fields` and output `path_field` values use simple dot paths through JSON objects:

```yaml
required_fields:
  - summary
  - diagnostics.sample_count
outputs:
  predictions:
    path_field: outputs.predictions
```

Given this report:

```json
{
  "summary": "Synthetic run completed.",
  "diagnostics": {"sample_count": 24},
  "outputs": {"predictions": "artifacts/predictions.csv"}
}
```

All three dot paths resolve. List indexing is intentionally not supported; keep contract-facing report fields object-shaped and stable.

## Threshold specifications

`counts`, `metrics`, and `numeric` are maps from value name to threshold object. Each threshold must include `min`, `max`, or both:

```yaml
counts:
  examples: {min: 1}
  failures: {max: 0}
metrics:
  accuracy: {min: 0.9}
  loss: {max: 1.0}
numeric:
  diagnostics.sample_count: {min: 20}
  quality.score: {min: 0.8, max: 1.0}
```

`counts` and `metrics` are shorthand for values under the report's top-level `counts` and `metrics` objects. Use `numeric` when your pipeline stores thresholds somewhere else in the report JSON. Values must be finite JSON numbers. Missing values, booleans, strings, `NaN`, and infinity-like values fail as invalid numeric evidence.

## Output specifications

Outputs connect a report field to an artifact path:

```yaml
outputs:
  predictions:
    path_field: outputs.predictions
    required: true
    csv_columns: [id, label, score]
```

The referenced report value must be a relative path string under the run root. Required missing artifacts fail; optional missing artifacts warn. Each output spec must be a mapping with a `path_field`; malformed output specs raise a clear `ValueError` during spec loading. When `csv_columns` is set, Evidence Gate reads only the CSV header and checks that every listed column is present. Missing columns fail with `table.column_missing`; unreadable or non-UTF-8 CSV files fail with `table.invalid_csv` instead of crashing validation. The old `columns` spelling is accepted as a backward-compatible alias, but new contracts should use `csv_columns` so the CSV-specific behavior is explicit.

## Path policy

All report and output paths must be relative and contained by the run directory. These are rejected:

```yaml
path: ABSOLUTE_PATH/report.json
path: ../outside/report.json
```

This keeps generated JSON and Markdown safe to share without embedding machine-specific absolute paths.

## Recommended report design

For agent- and reviewer-friendly evidence, prefer report JSON with these stable groups:

```json
{
  "status": "passed",
  "summary": "Synthetic evaluation completed.",
  "counts": {"examples": 24, "failures": 0},
  "metrics": {"accuracy": 0.96, "loss": 0.18},
  "outputs": {"predictions": "artifacts/predictions.csv"},
  "diagnostics": {"sample_count": 24}
}
```

Keep raw datasets, logs, and large artifacts out of JSON reports. Store them as files and reference them by relative path when they are part of the review evidence.
