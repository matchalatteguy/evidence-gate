# Failure codes and repair

Read `checks` in status JSON; `details` contains structured observations when a
check provides them. Scripts should use `code` and `severity`, not parse prose.

| Code family | Meaning | Repair |
| --- | --- | --- |
| `spec.empty` | Python API received no reports. | Load a non-empty contract. |
| `report.missing`, `report.invalid_json`, `report.status_mismatch` | Report absent, unreadable/invalid, or incomplete. | Inspect the producing stage. |
| `field.missing` | Declared required field absent. | Fix the report writer. |
| `count.invalid`, `metric.invalid`, `numeric.invalid` | Wrong type or nonfinite evidence; counts must be non-negative integers. | Correct the calculation/serialization. |
| `*.below_min`, `*.above_max` | Configured absolute limit missed. | Inspect the result; changing thresholds is a policy decision. |
| `artifact.missing`, `artifact.not_file` | Declared export absent or a directory. | Finish the export or correct its path. |
| `artifact.sha256_missing`, `artifact.sha256_invalid` | Expected digest absent/malformed. | Record the completed file's digest. |
| `artifact.sha256_mismatch`, `artifact.sha256_read_error` | Bytes changed or could not be hashed. | Regenerate/recover the artifact and investigate the writer. |
| `path.absolute`, `path.escape`, `baseline.path_escape` | Declared file is outside its run boundary. | Use contained relative paths. |
| `table.invalid_header`, `table.column_missing` | Empty/duplicate header names or absent configured columns. | Correct the CSV writer. |
| `table.invalid_csv`, `table.row_width` | Parser/read failure or inconsistent record widths. | Repair the export; partial counts cannot prove completeness. |
| `table.empty_cell`, `table.invalid_integer`, `table.invalid_number` | Required blank or invalid typed cells. | Inspect sampled row numbers without exposing raw values. |
| `table.value_below_min`, `table.value_above_max` | Numeric cell outside its limits. | Inspect producer values. |
| `table.row_count_below_min`, `table.row_count_above_max` | Observed data-record count outside limits. | Investigate missing/excess records. |
| `table.row_count_invalid`, `table.row_count_mismatch` | Producer count invalid or differs from actual CSV records. | Repair the export/count calculation. |
| `baseline.required`, `baseline.report_missing`, `baseline.invalid_json`, `baseline.status_mismatch` | Comparison reference unavailable/incomplete. | Supply the preserved reference run. |
| `baseline.same_run` | Candidate was supplied as its own reference. | Choose a separate reference snapshot. |
| `baseline.identity_invalid`, `baseline.identity_mismatch` | Dataset/configuration identity unavailable or different. | Use comparable inputs, then regenerate evidence. |
| `baseline.numeric_invalid` | Missing/nonfinite/wrong comparison type. | Fix candidate/reference numeric evidence. |
| `regression.increase`, `regression.decrease` | Directional change exceeded the configured tolerance. | Investigate the change before promotion. |

Optional missing reports use `report.optional_missing`; absent optional artifacts
use `artifact.missing` with warning severity. Present optional evidence must satisfy
its configured checks. `--strict-warnings` promotes warnings to failures while
preserving their codes.

Configuration and output-destination errors are CLI exit `2`, printed to stderr,
and do not produce a fresh validation status. The [CI recipe](ci-integration.md)
shows how to avoid using earlier approval files in that case.
