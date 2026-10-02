# Gate a model change against its previous run

This example evaluates a small keyword classifier on 100 synthetic support messages.
It computes predictions, correct counts, and accuracy from the classifier's output.
It then validates the actual CSV and compares accuracy against a reference evaluated
on the same dataset. There are no network calls or model dependencies.

From the repository root:

```bash
uv run python examples/model-promotion/run.py --output .runs/promotion --demonstrate-failure
```

From the installed package:

```bash
uvx --from 'git+https://github.com/matchalatteguy/evidence-gate.git@v0.4.0' evidence-gate init-example promotion --name model-promotion
uv run --with 'git+https://github.com/matchalatteguy/evidence-gate.git@v0.4.0' python promotion/run.py --output promotion/.runs/demo --demonstrate-failure
```

Use the Python environment in which Evidence Gate is installed. `uv tool install`
isolates the CLI; to run Python examples, use `uv run --with` or a virtual environment
as shown in the main README.

Expected decisions:

```text
regression: accuracy=0.80; needs_work; regression.decrease
truncated: accuracy=1.00; needs_work; table.row_count_below_min, table.row_count_mismatch
nonfinite: accuracy=1.00; needs_work; table.invalid_number
improved: accuracy=1.00; approved
```

The reference accuracy is 0.90. Every candidate satisfies the fixed accuracy floor
of 0.75. A regression limit of 0.02 catches the weaker classifier. Dataset fingerprints
must match before the metric comparison is usable. The truncated and nonfinite exports
have freshly computed, correct hashes: content checks detect failures that a hash cannot.

Each case writes the same validation decision to JSON, Markdown, and JUnit XML under
`OUTPUT/reviews/CASE/`, outside the candidate/reference bundles. Exit `0` means the
improved candidate passed; failures in the demonstration are expected and checked.
Individual `--case regression`, `--case truncated`, or `--case nonfinite` commands exit `1`.
The output directory must be new, preserving earlier runs.

The examples repeat ten invented messages to keep the decisions inspectable. These
results illustrate a promotion contract, not a measured ML benchmark or a production
classifier. Reported metrics and the chosen reference remain the producer's responsibility;
the gate does not independently recompute accuracy or authenticate the dataset.
