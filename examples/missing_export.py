"""Demonstrate a pipeline that reports success before its CSV export exists."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "evidence_gate.cli", *args],
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> None:
    with TemporaryDirectory(prefix="evidence-gate-demo-") as directory:
        project = Path(directory) / "example"
        copied = cli("init-example", str(project))
        if copied.returncode != 0:
            raise RuntimeError(copied.stderr)
        run = project / "runs" / "demo-run"
        predictions = run / "artifacts" / "predictions.csv"
        exported_csv = predictions.read_bytes()
        predictions.unlink()
        arguments = ("validate", "--spec", str(project / "evidence-gate.yaml"), "--run", str(run))

        incomplete = cli(*arguments)
        if incomplete.returncode != 1:
            raise RuntimeError(f"expected a gate failure: {incomplete.stderr or incomplete.stdout}")
        failures = [
            check["code"]
            for check in json.loads(incomplete.stdout)["checks"]
            if check["severity"] == "failure"
        ]
        print(f"Before export: exit {incomplete.returncode}; {', '.join(failures)}")

        # Finish the missing export; the reported metrics are unchanged.
        predictions.write_bytes(exported_csv)
        complete = cli(*arguments)
        if complete.returncode != 0:
            raise RuntimeError(complete.stderr or complete.stdout)
        result = json.loads(complete.stdout)
        print(
            f"After export:  exit {complete.returncode}; {result['recommendation']} ({result['counts']['total']} checks)"
        )


if __name__ == "__main__":
    main()
