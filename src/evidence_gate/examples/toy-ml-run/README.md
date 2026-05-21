# Toy ML run example

This directory is a synthetic, local-only example that demonstrates the smallest useful Evidence Gate workflow. It does not contain real data, service credentials, network calls, or private project context.

## Layout

```text
toy-ml-run/
  evidence-gate.yaml
  runs/demo-run/
    reports/metrics.json
    artifacts/predictions.csv
```

- `evidence-gate.yaml` declares the required report, metric thresholds, count thresholds, and expected CSV columns.
- `runs/demo-run/reports/metrics.json` is a synthetic run report with status, summary, counts, metrics, and output paths.
- `runs/demo-run/artifacts/predictions.csv` is a tiny synthetic artifact checked only by header columns.

## Run it

From the repository root:

```bash
uv run evidence-gate validate \
  --spec examples/toy-ml-run/evidence-gate.yaml \
  --run examples/toy-ml-run/runs/demo-run \
  --json-out reports/evidence-status.json

uv run evidence-gate packet \
  --status reports/evidence-status.json \
  --md-out reports/review-packet.md
```

The validation command should exit `0`. The generated packet is a local review artifact and can be removed or regenerated at any time.

## Adapt it for your own pipeline

1. Copy this directory with `evidence-gate init-example scratch/my-run` or by using your normal project template tooling.
2. Replace the synthetic report names and metrics with names from your own local pipeline.
3. Keep every report and artifact path relative to the run directory.
4. Add required fields and thresholds that prove the run is ready for human review.
5. Commit the contract and a tiny synthetic fixture; avoid committing large generated artifacts unless they are intentionally small examples.
