# Write completed evidence from your pipeline

Finish the artifacts, compute values from the work actually performed, record their
hashes, and write the JSON report last. A failed stage should leave no completion
report or report a status that the contract rejects.

```python
from pathlib import Path
from evidence_gate import output_sha256, write_report_atomic

run_root = Path("runs/candidate")
artifact = run_root / "artifacts/predictions.csv"
# Your pipeline has written and closed artifact, and computed these actual values.
report = {
    "status": "passed",
    "counts": {"examples": len(predictions)},
    "metrics": {"accuracy": correct / len(predictions)},
    "dataset_sha256": dataset_sha256,
    "outputs": {"predictions": "artifacts/predictions.csv"},
    "sha256": {"predictions": output_sha256(artifact)},
}
write_report_atomic(run_root / "reports/evaluation.json", report)
```

`output_sha256` reads in 1 MiB chunks. `write_report_atomic` accepts a JSON object,
rejects nonfinite/unsupported JSON values, and publishes via a temporary file in
the target directory followed by replacement. A failed serialization/write leaves
the previous target intact. This avoids readers observing a partially written
report. It is a single-file replacement, not a transaction across the artifacts;
stop artifact writers before validating. Producer helpers do not apply a run-root
containment policy: the producer owns its destination choices.

The [model promotion example](../examples/model-promotion/README.md) executes this
recipe. The gate independently counts CSV records and checks configured cells; it
still trusts the producer's metric calculations and dataset identities. Hashes
match the expected bytes supplied by that producer, not an authenticated source.
