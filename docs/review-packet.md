# Review packet

A review packet is the human-facing summary generated from a validation result. It gives a reviewer enough structure to see the decision, count checks, and inspect failures without reading every report file first.

## Generate a packet

```bash
uv run evidence-gate validate \
  --spec examples/toy-ml-run/evidence-gate.yaml \
  --run examples/toy-ml-run/runs/demo-run \
  --json-out reports/evidence-status.json

uv run evidence-gate packet \
  --status reports/evidence-status.json \
  --md-out reports/review-packet.md
```

## Status JSON

`validate --json-out` writes a machine-readable status object:

```json
{
  "passed": true,
  "recommendation": "approved",
  "counts": {"passed": 1, "warnings": 0, "failed": 0, "total": 1},
  "run_root": "demo-run",
  "checks": [
    {
      "code": "report.present",
      "message": "Report 'metrics' exists",
      "severity": "pass",
      "report": "metrics",
      "path": "reports/metrics.json"
    }
  ]
}
```

Important fields:

`packet` validates the status schema, boolean decision, check severities, and consistency of the decision and counts with the checks. Malformed or inconsistent status input returns exit `2` instead of rendering a misleading approval. This consistency check does not authenticate the status file or rerun validation.

- `passed`: true only when there are no failure-severity checks.
- `recommendation`: `approved` when passed, otherwise `needs_work`.
- `counts`: aggregate check counts for dashboards and CI logs.
- `run_root`: display name of the run directory, not an absolute path.
- `checks`: stable-code check details for downstream automation.

## Markdown packet contents

The Markdown packet includes:

- computed decision (`approved` or `needs_work`);
- aggregate check counts;
- passed checks;
- warnings;
- failures;
- evidence paths relative to the run directory.

It is designed to be pasted into a review issue, release checklist, pull request comment, or local decision note.

## How to interpret results

A packet with `approved` means the configured evidence contract passed. It does not mean the underlying model, dataset, benchmark, or document output is inherently good. Human review should still decide whether the reported evidence is meaningful.

A packet with `needs_work` means at least one required check failed. Common fixes are:

- write the missing report;
- correct the report `status` field;
- include a required JSON field;
- fix a count or metric threshold;
- keep artifact paths relative to the run root;
- create the declared output artifact;
- add missing CSV columns.

## Public-safe output

Generated packet paths are relative to the run root. Evidence Gate intentionally avoids embedding absolute local paths in review artifacts.
