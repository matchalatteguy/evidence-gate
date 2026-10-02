# CI: keep the failure report and stop promotion

Validate the contract before running an expensive producer:

```bash
evidence-gate check-spec --spec evidence-gate.yaml
```

After the producer finishes, run this step in your existing GitHub Actions job.
It assumes the environment already has Evidence Gate installed and both runs are
available. Use an immutable reference chosen by your project, not an arbitrary
latest run.

```yaml
- name: Gate candidate evidence
  shell: bash
  run: |
    if evidence-gate validate \
      --spec evidence-gate.yaml \
      --run runs/candidate \
      --baseline runs/reference \
      --strict-warnings \
      --json-out review/status.json \
      --md-out review/summary.md \
      --junit-out review/junit.xml; then
      gate_exit=0
    else
      gate_exit=$?
    fi
    if [ "$gate_exit" -eq 2 ]; then
      exit 2
    fi
    cat review/summary.md >> "$GITHUB_STEP_SUMMARY"
    exit "$gate_exit"
```

Exit `1` writes the failure decision to all requested reports before failing the
step. Exit `2` means validation did not produce a new decision; do not publish or
reuse an older status/review file. Output files must be distinct and outside both
run roots. Remove `--baseline` for contracts without regression checks.

GitHub documents [job summary files](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands#adding-a-job-summary)
as Markdown appended to `GITHUB_STEP_SUMMARY`. Evidence Gate only writes the paths
you request; it does not send comments, create checks, or call GitHub APIs.

JUnit maps each check to a testcase. Required failures are `<failure>`, optional
warnings are `<skipped>`, and passes have neither element. Strict warnings become
failures consistently in JSON, Markdown, JUnit, and the process exit. Configure your
existing CI test reporter/artifact upload step to run after failures as well.

The repository's own CI runs the promotion example and the built wheel outside the
checkout. That demonstrates the CLI and package resources, not your producer's
correctness or your project's baseline-selection policy.
