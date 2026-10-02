# LLM agent guide

Evidence Gate is intentionally simple enough for coding agents and review agents to use without hidden state. This guide describes a safe sequence for agents that create, validate, or review local run evidence.

## Agent contract

An agent should treat the evidence contract as the source of truth:

1. Read `evidence-gate.yaml` before inspecting run outputs.
2. Confirm every declared path is relative and under the run root.
3. Run `evidence-gate validate` after the pipeline writes reports and artifacts.
4. Inspect stable check codes in the status JSON before suggesting fixes.
5. Generate a Markdown packet only after validation.
6. Do not treat `approved` as a domain-quality judgment; it only means the configured evidence checks passed.

## Safe command sequence

```bash
uv run evidence-gate check-spec --spec evidence-gate.yaml
uv run evidence-gate validate \
  --spec evidence-gate.yaml \
  --run runs/demo-run \
  --json-out reports/evidence-status.json \
  --md-out reports/review-packet.md
```

If validation exits `1`, read `reports/evidence-status.json` and group fixes by check code. Typical remediation map:

If it exits `2`, ignore existing output files and repair stderr's input/contract/
destination error first. Do not treat an earlier packet as a new approval. Run
outputs must be outside candidate/reference bundles. For regressions, preserve a
deliberately chosen reference and pass `--baseline`; do not pick a weaker reference
or relax tolerances merely to obtain approval.

| Check code | Meaning | Agent action |
| --- | --- | --- |
| `report.missing` | A required report was not produced. | Re-run or fix the pipeline stage that writes the report. |
| `report.status_mismatch` | Report status differs from `expected_status`. | Inspect the report and decide whether the run is genuinely incomplete or the contract is stale. |
| `field.missing` | A configured JSON field is absent. | Add the field to the report writer or relax the contract if the field is not review-relevant. |
| `metric.below_min` / `metric.above_max` | A metric missed its threshold. | Surface the threshold miss to a human reviewer; do not silently lower thresholds. |
| `artifact.missing` | A declared output path does not exist. | Create the artifact or fix the report path. |
| `path.absolute` / `path.escape` | A path leaks outside the run root. | Replace it with a relative path contained by the run directory. |
| `table.column_missing` | CSV header lacks a required column. | Fix the artifact writer or update the column contract after review. |
| `table.row_count_mismatch` | Export count differs from the report. | Investigate the actual writer/count calculation. |
| `table.invalid_number` | A CSV numeric cell is invalid/nonfinite. | Inspect the bounded row diagnostics. |
| `baseline.identity_mismatch` | Reference dataset/configuration differs. | Obtain comparable evidence. |
| `regression.increase` / `regression.decrease` | Candidate change exceeds policy. | Surface the measured delta and limit; investigate the change. |

## Public-safety reminders

- Use synthetic examples in documentation and tests.
- Keep generated review artifacts local unless a human explicitly asks to commit them.
- Do not embed credentials, usernames, hostnames, absolute paths, or private project details in contracts or reports.
- Do not add live network, authentication, upload, or remote-mutation behavior around validation.
