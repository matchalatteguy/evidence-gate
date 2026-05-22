# QUALITYMAX_NOTES

Updated: 2026-05-21T23:14:54+08:00

## Scope inspected

- README.md
- pyproject.toml
- src/evidence_gate/*.py
- tests/*.py
- docs/python-api.md
- docs/cli-usage.md
- Existing public-safety and final-polish notes

## Reusable-polish changes

- Added `SpecValidationError` as a public API boundary for malformed evidence contracts.
- Hardened contract parsing in `src/evidence_gate/specs.py`:
  - required report/output fields now produce contextual errors such as `reports[0].name is required`;
  - list fields must be real lists of non-empty strings;
  - booleans must be real booleans instead of truthy/falsy coercions;
  - thresholds must be mappings with only `min`/`max` keys and finite numeric values.
- Improved CLI ergonomics in `src/evidence_gate/cli.py`:
  - malformed specs print `spec error: ...` and return exit code 2;
  - malformed status JSON prints `input error: ...` and returns exit code 2;
  - users no longer get tracebacks for common input mistakes.
- Exported `SpecValidationError` from `evidence_gate.__init__`.
- Removed fake placeholder project URLs from `pyproject.toml` so package metadata is not misleading before a real remote exists.
- Documented the spec-loading error boundary in `docs/python-api.md` and updated CLI exit behavior in `docs/cli-usage.md`.
- Added regression tests for contextual spec errors and concise CLI input-error handling.

## Exact commands run and results

```bash
uv run pytest tests/test_validation.py::test_missing_report_name_raises_contextual_spec_error tests/test_validation.py::test_invalid_threshold_shape_raises_contextual_spec_error tests/test_reports_and_cli.py::test_cli_validate_reports_spec_errors_without_traceback -q
```

Result: expected RED failure before implementation. Pytest could not collect the new tests because `SpecValidationError` and `SPEC_ERROR_EXIT_CODE` were not implemented/exported yet.

```bash
uv run pytest tests/test_validation.py::test_missing_report_name_raises_contextual_spec_error tests/test_validation.py::test_invalid_threshold_shape_raises_contextual_spec_error tests/test_reports_and_cli.py::test_cli_validate_reports_spec_errors_without_traceback -q
```

Result after implementation: passed, `3 passed`.

```bash
uv run pytest
```

Result: passed, `24 passed in 0.07s`.

```bash
uv run ruff check .
```

Result before formatting fix: failed with one `I001` import-order issue in `src/evidence_gate/cli.py`.

```bash
uv run ruff check . --fix
```

Result: fixed the import-order issue, `Found 1 error (1 fixed, 0 remaining)`.

```bash
uv run pytest && uv run ruff check .
```

Result after adding malformed-status JSON coverage and docs updates: passed, `25 passed in 0.08s`; `All checks passed!`.

```bash
uv build
```

Result: passed. Built `dist/evidence_gate-0.1.0.tar.gz` and `dist/evidence_gate-0.1.0-py3-none-any.whl`.

```bash
uv run pytest && uv run ruff check . && uv build
```

Final verification result: passed. `25 passed in 0.07s`; `All checks passed!`; built `dist/evidence_gate-0.1.0.tar.gz` and `dist/evidence_gate-0.1.0-py3-none-any.whl`.

```bash
date -Iseconds
```

Result: `2026-05-21T23:14:54+08:00`.

## Public-safety scan

Used repo content search for private project terms, local path tokens, placeholder package URLs, and common secret-shaped words.

Result: no new private/local/project-specific leaks found in code, tests, package metadata, or docs. Remaining matches are pre-existing safety-review prose and generic non-goals guidance about avoiding secrets/private context.

## Readiness

Ready for docs/safety/review gates. The repository remains a local-first, public-safe reusable Python library/CLI candidate with stronger spec parsing, clearer API errors, improved CLI behavior, and passing pytest/ruff/build checks.

## Test-gate follow-up — 2026-05-22T01:18:01+08:00

### Added/strengthened tests

- Added CLI packet coverage for structurally malformed status JSON so valid JSON with the wrong shape returns exit code 2 without a traceback.
- Added a real subprocess CLI validate smoke test through `python -m evidence_gate.cli` to verify process exit code, stderr, and status JSON output.
- Added symlink path-containment coverage for artifacts that appear under the run root but resolve outside it.
- Added mixed multi-report coverage to preserve required failures and optional warnings in one validation result.

### Exact commands run and results

```bash
uv run pytest tests/test_reports_and_cli.py::test_cli_packet_reports_malformed_status_shape_without_traceback -q
```

Result: expected RED failure before CLI hardening. The test raised `KeyError: 'passed'` from `ValidationResult.from_dict()` instead of returning a concise input error.

```bash
uv run pytest tests/test_reports_and_cli.py::test_cli_packet_reports_malformed_status_shape_without_traceback -q
```

Result after implementation: passed, `1 passed`.

```bash
uv run pytest tests/test_reports_and_cli.py::test_cli_packet_reports_malformed_status_shape_without_traceback tests/test_reports_and_cli.py::test_subprocess_cli_validate_exit_codes_and_streams tests/test_validation.py::test_output_symlink_escaping_run_root_fails tests/test_validation.py::test_multiple_reports_preserve_mixed_failures_and_warnings -q
```

Result: passed, `4 passed`.

```bash
uv run pytest && uv run ruff check . && uv build && printf 'import evidence_gate\nprint(evidence_gate.__name__)\n' | uv run python && uv run evidence-gate --help && tmpdir=$(mktemp -d) && uv run evidence-gate init-example "$tmpdir/example" && uv run evidence-gate validate --spec "$tmpdir/example/evidence-gate.yaml" --run "$tmpdir/example/runs/demo-run" --json-out "$tmpdir/status.json" && uv run evidence-gate packet --status "$tmpdir/status.json" --md-out "$tmpdir/review-packet.md" && test -s "$tmpdir/review-packet.md" && printf 'example path OK: %s\n' "$tmpdir"
```

Result: passed. `33 passed in 0.22s`; `All checks passed!`; built `dist/evidence_gate-0.1.0.tar.gz` and `dist/evidence_gate-0.1.0-py3-none-any.whl`; package import printed `evidence_gate`; CLI help printed the `validate`, `packet`, and `init-example` commands; realistic init-example/validate/packet path completed in a temporary directory.

```bash
date -Iseconds
```

Result: `2026-05-22T01:18:01+08:00`.

### Remaining risks

- This test-gate run verified tests, ruff, build, import, CLI help, and a realistic example path, but did not resolve broader release-readiness items such as clean public git metadata/history, tracked generated report policy, or final public remote readiness.
- `dist/` artifacts were regenerated by `uv build` and remain local ignored build outputs; do not publish them unless the release process explicitly wants them.

## Test-gate verification addendum — 2026-05-22T01:18:44+08:00

### Additional tests and fixes from this run

- Added/kept high-value tests for structurally malformed status JSON, subprocess CLI `validate` success/failure behavior, symlink containment, mixed warning/failure multi-report results, and explicit packet rendering/writing API behavior.
- Fixed syntax regressions observed in `src/evidence_gate/reports.py` and `src/evidence_gate/cli.py` while preserving the polishing changes already present in the working tree.
- Updated the existing `init-example` overwrite test for the current non-traceback exit-code-2 behavior.

### Exact commands run and results

```bash
uv run pytest tests/test_reports_and_cli.py::test_cli_packet_reports_malformed_status_shape_without_traceback -q
```

Result: expected RED failure before CLI hardening. The test raised `KeyError: 'passed'` from `ValidationResult.from_dict()` instead of returning a concise input error.

```bash
uv run pytest tests/test_reports_and_cli.py::test_cli_packet_reports_malformed_status_shape_without_traceback tests/test_reports_and_cli.py::test_subprocess_cli_validate_success_outputs_json tests/test_reports_and_cli.py::test_subprocess_cli_validate_required_failure_exits_one tests/test_validation.py::test_symlink_output_escaping_run_root_fails tests/test_validation.py::test_mixed_reports_count_failures_warnings_and_passes -q
```

Result after implementation/syntax repair: passed, `5 passed`.

```bash
set -euo pipefail
printf 'import evidence_gate; print(evidence_gate.__name__)\n' | uv run python
uv run evidence-gate --help
uv run pytest
uv run ruff check .
uv build
TMPDIR=$(mktemp -d)
uv run evidence-gate init-example "$TMPDIR/copied-example"
uv run evidence-gate validate --spec "$TMPDIR/copied-example/evidence-gate.yaml" --run "$TMPDIR/copied-example/runs/demo-run" --json-out "$TMPDIR/status.json"
uv run evidence-gate packet --status "$TMPDIR/status.json" --md-out "$TMPDIR/review-packet.md"
test -s "$TMPDIR/status.json" && test -s "$TMPDIR/review-packet.md"
python3 - <<'PY' "$TMPDIR/status.json" "$TMPDIR/review-packet.md"
import json, sys
status = json.load(open(sys.argv[1], encoding='utf-8'))
packet = open(sys.argv[2], encoding='utf-8').read()
print(status['passed'], status['recommendation'])
print(packet.splitlines()[0])
PY
```

Result: passed. Import printed `evidence_gate`; CLI help listed `validate`, `packet`, and `init-example`; `36 passed in 0.25s`; `All checks passed!`; `uv build` rebuilt `dist/evidence_gate-0.1.0.tar.gz` and `dist/evidence_gate-0.1.0-py3-none-any.whl`; realistic `init-example` → `validate` → `packet` path printed `True approved` and `# Evidence Review Packet`.

```bash
set -euo pipefail
TMPDIR=$(mktemp -d)
uv venv "$TMPDIR/venv" >/dev/null
uv pip install --python "$TMPDIR/venv/bin/python" dist/evidence_gate-0.1.0-py3-none-any.whl >/dev/null
"$TMPDIR/venv/bin/evidence-gate" init-example "$TMPDIR/example"
"$TMPDIR/venv/bin/evidence-gate" validate --spec "$TMPDIR/example/evidence-gate.yaml" --run "$TMPDIR/example/runs/demo-run" --json-out "$TMPDIR/status.json"
"$TMPDIR/venv/bin/python" - <<'PY' "$TMPDIR/status.json"
import json, sys
payload = json.load(open(sys.argv[1], encoding='utf-8'))
print(payload['passed'], payload['recommendation'])
PY
```

Result: passed. Fresh uv venv installed the built wheel plus `pyyaml==6.0.3`, then installed-console `evidence-gate` copied and validated the bundled example, printing `True approved`.

```bash
date -Iseconds
```

Result: `2026-05-22T01:18:44+08:00`.

### Remaining risks

- Working tree remains intentionally modified for review by upstream polish/refinement gates; this test gate did not commit changes or rewrite public git metadata/history.
- Broader release-readiness items remain outside this test gate: clean generic git metadata, tracked generated report policy, final safety review, and public remote readiness.
- `dist/` artifacts were regenerated by `uv build` and remain local build outputs.

## Final test-gate correction — 2026-05-22T01:20:36+08:00

After the previous addendum, additional in-flight tests for schema version, arbitrary numeric dot-path thresholds, `csv_columns`, and empty threshold maps were present in the working tree. I corrected the numeric-threshold test fixture indentation and a ruff `RUF043` regex warning, then reran the full gate.

```bash
uv run pytest && uv run ruff check .
```

Intermediate result: pytest passed with `43 passed in 0.24s`; ruff failed on `RUF043` in `tests/test_validation.py` for an unescaped regex in `pytest.raises(..., match=...)`. Fixed by using a raw escaped regex.

```bash
set -euo pipefail
printf 'import evidence_gate; print(evidence_gate.__name__)\n' | uv run python
uv run evidence-gate --help
uv run pytest
uv run ruff check .
uv build
TMPDIR=$(mktemp -d)
uv run evidence-gate init-example "$TMPDIR/copied-example"
uv run evidence-gate validate --spec "$TMPDIR/copied-example/evidence-gate.yaml" --run "$TMPDIR/copied-example/runs/demo-run" --json-out "$TMPDIR/status.json"
uv run evidence-gate packet --status "$TMPDIR/status.json" --md-out "$TMPDIR/review-packet.md"
test -s "$TMPDIR/status.json" && test -s "$TMPDIR/review-packet.md"
python3 - <<'PY' "$TMPDIR/status.json" "$TMPDIR/review-packet.md"
import json, sys
status = json.load(open(sys.argv[1], encoding='utf-8'))
packet = open(sys.argv[2], encoding='utf-8').read()
print(status['passed'], status['recommendation'])
print(packet.splitlines()[0])
PY
```

Final result: passed. Import printed `evidence_gate`; CLI help printed successfully; pytest reported `43 passed in 0.25s`; ruff reported `All checks passed!`; `uv build` rebuilt both sdist and wheel; realistic `init-example` → `validate` → `packet` path printed `True approved` and `# Evidence Review Packet`.

```bash
set -euo pipefail
TMPDIR=$(mktemp -d)
uv venv "$TMPDIR/venv" >/dev/null
uv pip install --python "$TMPDIR/venv/bin/python" dist/evidence_gate-0.1.0-py3-none-any.whl >/dev/null
"$TMPDIR/venv/bin/evidence-gate" init-example "$TMPDIR/example"
"$TMPDIR/venv/bin/evidence-gate" validate --spec "$TMPDIR/example/evidence-gate.yaml" --run "$TMPDIR/example/runs/demo-run" --json-out "$TMPDIR/status.json"
"$TMPDIR/venv/bin/python" - <<'PY' "$TMPDIR/status.json"
import json, sys
payload = json.load(open(sys.argv[1], encoding='utf-8'))
print(payload['passed'], payload['recommendation'])
PY
```

Final wheel-install result: passed. Fresh uv venv installed `evidence-gate==0.1.0` from the built wheel and `pyyaml==6.0.3`; installed console script validated the bundled example and printed `True approved`.


## 90+ readiness delta - 2026-05-22T01:21:09+08:00

Focused changes made from the 81/100 architecture/usefulness audit:

- Added an explicit contract `schema_version` field with default/support for version `1`, validation for unsupported versions, and schema version propagation into status JSON and Markdown review packets.
- Added reusable arbitrary numeric dot-path thresholds via report-level `numeric`, so contracts are no longer limited to hard-coded top-level `counts` and `metrics` groups.
- Made CSV artifact validation explicit with `csv_columns`, while retaining `columns` as a backward-compatible alias for older contracts.
- Split packet rendering/writing into stable public APIs: `render_review_packet(result)` for pure Markdown rendering and `write_review_packet_file(result, path)` for direct file-path writing aligned with CLI `--md-out`; the older directory helper remains compatible.
- Hardened `packet` and `init-example` CLI boundaries so malformed status shape and existing targets return exit code 2 with concise stderr instead of tracebacks/SystemExit surprises.
- Added `py.typed` for typed API consumers.
- Added `.github/workflows/ci.yml` with pytest, ruff, package build, and CLI smoke test on Python 3.11/3.12.
- Updated README and schema/API/CLI docs to explain fit/non-fit cases, schema versioning, arbitrary numeric checks, explicit CSV columns, CI workflow, and pure packet rendering.
- Updated bundled/root toy contracts to use `schema_version: 1` and `csv_columns`.
- Added regression tests for schema versioning, arbitrary numeric thresholds, explicit CSV columns, packet writer/render APIs, malformed status shape, existing-target CLI behavior, subprocess CLI behavior, wheel install smoke path, symlink path containment, multi-report/mixed warning behavior, and typed package marker coverage already present in the expanded suite.

### Exact commands run and results

```bash
uv run pytest -q
```

Result after core implementation but before updating the legacy init-example test: failed with `test_cli_init_example_refuses_existing_target` expecting `SystemExit`; this confirmed the intended CLI behavior changed to return exit code 2 without traceback.

```bash
uv run pytest -q
```

Result after updating/adding tests: passed, `43 passed`.

```bash
uv run ruff check .
```

Result: passed, `All checks passed!`.

```bash
uv build
```

Result: passed. Built `dist/evidence_gate-0.1.0.tar.gz` and `dist/evidence_gate-0.1.0-py3-none-any.whl`.

```bash
tmpdir=$(mktemp -d) && uv venv "$tmpdir/venv" >/dev/null && uv pip install --python "$tmpdir/venv/bin/python" dist/evidence_gate-0.1.0-py3-none-any.whl >/dev/null && "$tmpdir/venv/bin/evidence-gate" init-example "$tmpdir/example" && "$tmpdir/venv/bin/evidence-gate" validate --spec "$tmpdir/example/evidence-gate.yaml" --run "$tmpdir/example/runs/demo-run" --json-out "$tmpdir/status.json" && "$tmpdir/venv/bin/evidence-gate" packet --status "$tmpdir/status.json" --md-out "$tmpdir/packet.md" && test -s "$tmpdir/packet.md" && echo "wheel smoke ok: $tmpdir"
```

Result: passed, printed a temporary wheel-smoke directory path.

```bash
repo content searches for private project names, personal usernames, local home paths, hostnames, source-repository names, and common secret-marker strings
```

Result: no private/local/project-specific matches; secret-word matches are generic safety-review/non-goals prose only.

### Expected score impact

Expected outsider usefulness/genericity/reusability score after this pass: about 91/100. The repo now has a clearer stable schema boundary, more reusable numeric checks, better API/CLI seams, CI/build/install evidence, and more public-facing docs. Remaining gap to 95+ is mostly release hygiene outside code functionality: clean/squashed generic git metadata before publication, final human review of uncommitted changes, and broader real-world examples beyond the toy run.
