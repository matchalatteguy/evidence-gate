# QUALITYMAX 90+ readiness

Updated: 2026-05-22T01:21:09+08:00

## Expected score

Expected architecture/usefulness/public-reusability score after this refinement pass: 91/100.

This is a practical 90+ public-candidate state, not a final 95+ release claim. The repository is now easier for a stranger to understand, install, test, and reuse as a small local evidence-contract validator.

## Improvements made

- Stable schema boundary:
  - contracts now support `schema_version: 1`;
  - unsupported schema versions fail during spec loading with a concise `SpecValidationError`;
  - validation status JSON and Markdown packets include the schema version.
- More reusable validation model:
  - added report-level `numeric` checks for arbitrary JSON dot paths, avoiding the previous limitation where thresholds only worked under top-level `counts` and `metrics`;
  - kept `counts` and `metrics` as convenient shorthand for common report layouts.
- Clearer artifact validation API:
  - added explicit `csv_columns` for CSV header checks;
  - retained `columns` as a backward-compatible alias so older contracts do not break.
- Cleaner public API/CLI seam:
  - added `render_review_packet(result)` for pure Markdown rendering;
  - added `write_review_packet_file(result, path)` for explicit file-path packet writing aligned with CLI `packet --md-out`;
  - retained the old directory-based `write_review_packet` helper for compatibility;
  - hardened malformed status-shape handling and existing `init-example` target behavior to return exit code 2 without tracebacks.
- Packaging/typing/CI hardening:
  - added `src/evidence_gate/py.typed`;
  - added `.github/workflows/ci.yml` with pytest, ruff, build, and CLI smoke checks on Python 3.11/3.12;
  - verified wheel install plus `init-example`, `validate`, and `packet` in a fresh uv venv.
- Documentation improvements:
  - README now includes fit/non-fit guidance for strangers evaluating whether to adopt the tool;
  - schema docs now cover schema versioning, arbitrary numeric thresholds, and explicit CSV header validation;
  - API docs now document pure rendering/file-writing helpers and `numeric.*` failure codes;
  - CLI docs now point to the included GitHub Actions workflow.
- Example updates:
  - root and packaged toy contracts now use `schema_version: 1` and `csv_columns`.

## Verification commands/results

- `uv run pytest -q` -> passed, 43 tests.
- `uv run ruff check .` -> passed, `All checks passed!`.
- `uv build` -> passed, built sdist and wheel under `dist/`.
- Fresh wheel smoke test with uv venv + installed wheel + `evidence-gate init-example` + `validate` + `packet` -> passed.
- Public-safety content searches for private/local terms and common secret-shaped terms -> no private/local/project-specific matches; remaining secret-word matches are generic safety/non-goals prose.

## Remaining gaps before 95+

- Human review is still required before treating these uncommitted changes as accepted.
- The documented git metadata/publication hold remains out of scope for code editing; before publishing, history should be squashed or rebuilt with generic public-safe metadata and verified from a clean clone.
- The toy example is now stronger, but a 95+ repository would benefit from one or two additional synthetic example directories, such as benchmark evaluation and document-processing/data-build workflows.
- A release checklist or changelog would further improve maintainability for a public package.
