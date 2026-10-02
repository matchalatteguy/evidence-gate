# Python API usage

Evidence Gate exposes a small API for scripts, notebooks, and LLM agents that need to validate local run evidence before review.

## Main objects

- `EvidenceSpec`: normalized contract containing report specifications and `schema_version`.
- `ReportSpec`: expected JSON report, required fields, thresholds, and output artifacts.
- `OutputSpec`: artifact path field, optional header/content checks, and producer digest field.
- `CsvSpec`, `CsvColumnSpec`: streaming record/count/type/range requirements.
- `RegressionSpec`: absolute increase/decrease limits for explicitly selected metrics.
- `RunBundle`: safe wrapper around a run root directory.
- `ValidationResult`: pass/fail result, recommendation, counts, checks, warnings, and failures.
- `Check`: one machine-readable check with stable code, severity, and optional structured `details`.
- `SpecValidationError`: raised by `load_spec` when a contract has an invalid shape.

## Basic usage

```python
from pathlib import Path

from evidence_gate import RunBundle, load_spec, render_review_packet, validate_run

spec = load_spec(Path("evidence-gate.yaml"))
bundle = RunBundle(Path("runs/demo-run"))
result = validate_run(bundle, spec)

print(result.passed)
print(result.recommendation)
print(result.counts)

for check in result.failures:
    print(check.code, check.message, check.path)

print(render_review_packet(result))
```

With comparison and warning policy:

```python
result = validate_run(
    bundle, spec, baseline=RunBundle(Path("runs/reference")), strict_warnings=True
)
```

No baseline comparisons are inferred: configure `ReportSpec.regressions` in the
contract. `baseline_match_fields` checks declared context equality first. The
reference is comparison evidence, not a claim of previously approved results.
Use `load_spec` to validate contract shapes before invoking the typed API.

## Handling failures

Use stable check codes for automation and human-readable messages for logs:

```python
if not result.passed:
    failure_codes = {check.code for check in result.failures}
    if "artifact.missing" in failure_codes:
        print("The run did not produce every required output artifact.")
```

Common failure codes include:

- `report.missing`
- `report.invalid_json`
- `report.status_mismatch`
- `field.missing`
- `count.invalid`, `count.below_min`, `count.above_max`
- `metric.invalid`, `metric.below_min`, `metric.above_max`
- `numeric.invalid`, `numeric.below_min`, `numeric.above_max`
- `artifact.missing`
- `artifact.sha256_missing`, `artifact.sha256_invalid`
- `artifact.sha256_mismatch`, `artifact.sha256_read_error`
- `path.absolute`, `path.escape`
- `table.column_missing`
- `table.invalid_header`, `table.invalid_csv`, `table.row_width`
- `table.empty_cell`, `table.invalid_integer`, `table.invalid_number`
- `table.row_count_mismatch`, `table.row_count_invalid`
- `baseline.required`, `baseline.identity_mismatch`, `baseline.numeric_invalid`
- `regression.increase`, `regression.decrease`

[All failure codes](failure-codes.md).

## Safe path resolution

`RunBundle` resolves report and artifact paths relative to its root:

```python
bundle = RunBundle(Path("runs/demo-run"))
path = bundle.resolve_relative("reports/metrics.json")
```

Absolute paths and paths that escape the run root raise `ValueError`. The validator converts those path errors into failure checks.

## Handling contract loading errors

`load_spec` raises `SpecValidationError` for malformed YAML/JSON contracts with messages that include the contract location when available:

```python
from pathlib import Path

from evidence_gate import SpecValidationError, load_spec

try:
    spec = load_spec(Path("evidence-gate.yaml"))
except SpecValidationError as exc:
    print(f"Fix the evidence contract: {exc}")
```

The CLI reports these as concise `spec error: ...` messages and exits with code `2` instead of printing a traceback.

## Writing artifacts

`render_review_packet(result)` returns Markdown without writing to disk. `write_review_packet_file(result, path)` writes to an explicit file path, matching the CLI `packet --md-out` behavior. `write_review_packet(result, output_dir, markdown=True)` remains available for callers that prefer the older directory-based helper.

`render_junit_xml(result)` returns JUnit XML; `write_junit_xml(result, path)` writes it.
All public renderers validate decision/count consistency before formatting, and
atomic file writers avoid partial individual outputs. Markdown escapes producer
text and bounds displayed details; JSON/JUnit retain structured details.

For producer reports, `output_sha256(path)` hashes file bytes in chunks and
`write_report_atomic(path, payload)` publishes a finite JSON object after successful
serialization. [Producer guide](producer-guide.md).

For machine-readable output, use `ValidationResult.to_dict()`. `Check.details`
appears only when present. Existing status schema `1` and contracts remain supported;
new keys/features require package version 0.4+.

## Agent usage tips

When an LLM agent uses Evidence Gate, it should:

1. Inspect or create the evidence contract first.
2. Run validation after the pipeline writes reports.
3. Read `result.failures` before proposing remediation.
4. Generate a Markdown packet only after validation.
5. Treat `approved` as evidence readiness, not as a replacement for domain review.
