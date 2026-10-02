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
| `regressions` | map of dot paths to tolerance objects | no | Compare numeric values with the same report path in `--baseline`. |
| `baseline_match_fields` | list of dot paths | no | Require identical non-null scalar context fields in candidate/reference before comparing metrics; requires `regressions`. |

Report files must contain JSON objects. Arrays, strings, and malformed JSON fail with `report.invalid_json`.

The report list must be non-empty and report names must be unique. Unknown or duplicate contract fields are errors rather than silently ignored checks. Optional maps must be mappings when supplied; `[]` and `null` are not empty maps. A threshold's `min` cannot exceed its `max`. Duplicate JSON report fields also fail validation.

## Dot paths

`required_fields`, output `path_field`, and output `sha256_field` values use simple dot paths through JSON objects:

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

### Output byte integrity

Set `sha256_field` to the dotted field containing the producer's expected file digest:

```yaml
outputs:
  predictions:
    path_field: outputs.predictions
    sha256_field: sha256.predictions
    csv_columns: [id, label, score]
```

The field name must be a non-empty string with non-empty dotted components and no surrounding component whitespace. The expected report value must contain exactly 64 hexadecimal characters; uppercase and lowercase are accepted. A producer can record the digest after completing its output:

```python
import hashlib

# report already contains outputs.predictions; run_root is the run directory.
with (run_root / report["outputs"]["predictions"]).open("rb") as source:
    report["sha256"] = {
        "predictions": hashlib.file_digest(source, "sha256").hexdigest()
    }
# Write this report after the export is closed and the digest is recorded.
```

Validation reads the artifact in 1 MiB chunks. A matching digest adds `artifact.sha256_match`. Missing fields, malformed digests, changed bytes, and read errors fail with `artifact.sha256_missing`, `artifact.sha256_invalid`, `artifact.sha256_mismatch`, and `artifact.sha256_read_error`, respectively.

Without this option, existing presence/header checks are unchanged. A missing optional artifact still warns without requiring a digest; a present optional artifact must satisfy its configured digest. The hash binds bytes to a trusted producer report. It does not authenticate that report or its sources, establish semantic correctness, or validate the artifact's content/schema. Preserve exports and their producer report together, and stop writers before validating.

## Path policy

Paths must be non-empty strings. Output artifacts must be files; a directory fails with `artifact.not_file` even when no CSV columns are requested. Unreadable or non-UTF-8 reports fail with `report.invalid_json`.

All report and output paths must be relative and contained by the run directory. These are rejected:

```yaml
path: ABSOLUTE_PATH/report.json
path: ../outside/report.json
```

This keeps generated JSON and Markdown safe to share without embedding machine-specific absolute paths.

## Full CSV content checks (0.4+)

Set `csv` to enable a complete streaming scan. Even `csv: {}` checks non-empty,
unique header names and every record's width, using Python's strict CSV reader.
Extra columns are allowed; configured columns must exist. Quoted commas/newlines
are supported. UTF-8, comma separation, and a header are required. A blank record
is a malformed-width record. A parser/read failure blocks approval and marks any
partial row count incomplete. CSV's standard field-size limit applies.

```yaml
outputs:
  predictions:
    path_field: outputs.predictions
    csv:
      rows: {min: 100, max: 100000}
      row_count_field: counts.examples
      columns:
        id: {type: integer, min: 0}
        score: {type: number, min: 0, max: 1}
        label: {type: string}
        note: {type: string, non_empty: false}
```

| CSV field | Default | Meaning |
| --- | --- | --- |
| `rows` | absent | Inclusive `min`/`max` non-negative integer data-record counts. Header excluded, multiline records count once. |
| `row_count_field` | absent | Dot path to a producer count; it must be a non-negative integer exactly equal to observed records. |
| `columns` | `{}` | Required column names mapped to type and value rules. |
| Column `type` | `string` | `string`, `integer`, or `number`. |
| Column `non_empty` | `true` | Reject empty/whitespace-only cells. `false` permits blanks, which skip type validation. |
| Column `min`/`max` | absent | Inclusive finite numeric limits; require a numeric type and `non_empty: true`. |

Integer cells use signed/unsigned ASCII digits. Number cells use finite decimal or
scientific ASCII notation, allowing surrounding whitespace for numbers. Integer
cells have no surrounding whitespace. Underscores and Unicode digits are rejected.
Numeric comparisons preserve integer and decimal precision.
Configured columns are required even with `non_empty: false`; that option permits
blank cells, not absent columns. This does not check key uniqueness or whether row
values agree with another artifact's contents.

Errors are aggregated by type with occurrence counts and at most five starting
physical line numbers and column names. Raw cell values are excluded. Memory holds
the current record, header/rules, and bounded diagnostic samples. An unsuccessful
scan never receives `table.content`; independently passing row counts do not erase
content failures. Combine content checks with `sha256_field` for both content and
producer-reported byte integrity. The legacy `csv_columns`/`columns` output keys
continue to check headers only when `csv` is absent.

## Baseline regressions (0.4+)

```yaml
baseline_match_fields: [dataset_sha256, evaluation.config_version]
regressions:
  metrics.accuracy: {max_decrease: 0.02}
  metrics.latency_ms: {max_increase: 5}
  numeric.error_count: {max_increase: 0}
```

Pass `--baseline runs/reference` to `validate`, or `baseline=RunBundle(...)` to
`validate_run`. Candidate and reference roots must differ. Both reports use the
configured relative `path`; reference paths obey containment rules too. A configured
`expected_status` applies to the reference report before comparisons.

Each tolerance must contain `max_increase`, `max_decrease`, or both, with finite,
non-negative numeric values. Limits are absolute in the metric's original units,
inclusive at the boundary. `delta = candidate - baseline`; an increase exceeds its
limit when `delta > max_increase`, a decrease when `-delta > max_decrease`.
Zero and negative reference values work because there is no relative division.
No implicit metric direction or percentage conversion is applied.

Missing/nonfinite/nonnumeric values, numeric strings, and booleans fail. Exact
decimal subtraction is isolated from the caller's Decimal context. Results include
candidate/reference values, exact delta/limits as decimal strings, field path, and
candidate/reference directory names in `Check.details`. Check messages explain the
comparison in the same units.

Match fields must exist as non-null finite scalars with the same JSON scalar type
and value; for example integer `1` differs from number `1.0`. Arrays/objects are
not identity fields. Failed identity matching prevents metric comparison. Values
are not dumped into identity diagnostics. Omitting match fields allows comparison
without a context identity guard: configure the dataset/configuration fields your
pipeline needs for a meaningful comparison.

The reference is trusted comparison evidence. It is not revalidated against the
entire candidate contract, and this feature does not establish previous approval,
source authenticity, statistical significance, or an appropriate baseline choice.
Preserve reference files and choose them deliberately. An absent optional candidate
report retains its warning behavior; use strict warnings if absence should block.

### Numeric representation

JSON report/spec decimal literals must round-trip through Python's native float
representation without changing their stated decimal value. For example `0.1`
and ordinary `json.dumps` float output are supported; `0.100000000000000005`,
overflow, and underflow literals fail parsing instead of silently collapsing
distinct metrics or identity values. YAML float limits obey the same policy and
use ordinary decimal/scientific notation. Integer limits are preserved exactly.
Configured numeric strings are invalid metrics; represent high-precision measures
in integer units if they cannot use the supported decimal representation.
Direct Python API comparisons operate on the Python values supplied by the caller.

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
