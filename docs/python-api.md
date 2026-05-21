# Python API usage

Evidence Gate exposes a small API for scripts, notebooks, and LLM agents that need to validate local run evidence before review.

## Main objects

- `EvidenceSpec`: normalized contract containing report specifications.
- `ReportSpec`: expected JSON report, required fields, thresholds, and output artifacts.
- `RunBundle`: safe wrapper around a run root directory.
- `ValidationResult`: pass/fail result, recommendation, counts, checks, warnings, and failures.
- `Check`: one machine-readable check with a stable code and severity.

## Basic usage

```python
from pathlib import Path

from evidence_gate import RunBundle, load_spec, validate_run, write_review_packet

spec = load_spec(Path("evidence-gate.yaml"))
bundle = RunBundle(Path("runs/demo-run"))
result = validate_run(bundle, spec)

print(result.passed)
print(result.recommendation)
print(result.counts)

for check in result.failures:
    print(check.code, check.message, check.path)

write_review_packet(result, Path("reports"), markdown=True)
```

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
- `artifact.missing`
- `path.absolute`, `path.escape`
- `table.column_missing`

## Safe path resolution

`RunBundle` resolves report and artifact paths relative to its root:

```python
bundle = RunBundle(Path("runs/demo-run"))
path = bundle.resolve_relative("reports/metrics.json")
```

Absolute paths and paths that escape the run root raise `ValueError`. The validator converts those path errors into failure checks.

## Writing artifacts

`write_review_packet(result, output_dir, markdown=True)` writes review artifacts under `output_dir`. The CLI uses this function to produce Markdown packets from status JSON.

For machine-readable output, use `ValidationResult.to_dict()` and serialize it with your preferred JSON writer.

## Agent usage tips

When an LLM agent uses Evidence Gate, it should:

1. Inspect or create the evidence contract first.
2. Run validation after the pipeline writes reports.
3. Read `result.failures` before proposing remediation.
4. Generate a Markdown packet only after validation.
5. Treat `approved` as evidence readiness, not as a replacement for domain review.
