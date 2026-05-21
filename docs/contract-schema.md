# Contract schema

An Evidence Gate contract declares reports that should exist inside a run directory and the checks
that make those reports review-ready.

## Top-level fields

- `reports`: list of report specifications.

## Report specification

- `name`: stable report name used in check messages.
- `path`: relative path from the run root to a JSON report.
- `required`: when true, missing reports fail the run; when false, they produce warnings.
- `expected_status`: optional value matched against the report's `status` field.
- `required_fields`: dot-paths that must exist in the JSON object.
- `counts`: numeric thresholds for count values.
- `metrics`: numeric thresholds for metric values.
- `outputs`: named artifacts referenced from the report.

All report and output paths must be relative and stay inside the run directory.
