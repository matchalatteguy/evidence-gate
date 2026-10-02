# Changelog

## 0.3.0 — 2026-10-02

- Add a reproducible input-contract → replay-comparison → evidence-review example
  with companion repositories pinned to immutable commits.
- Exercise incomplete exports, duplicate input events, missing future markouts,
  and refusal to overwrite earlier runs in a separate integration CI job.
- Add optional output `sha256_field` checks, using chunked file hashing. Missing or
  malformed expected digests, mismatches, and read errors fail validation.
- Bind all four replay exports to their producer-recorded hashes, with regressions
  for truncated CSVs and empty/tampered JSON, Markdown, and input-contract reports.
- Keep the standalone checker's runtime dependencies unchanged.

Compatibility: contract schema remains `1`. Outputs without `sha256_field` retain
their existing presence/header behavior. Absent optional outputs still warn; when
present, a configured digest must validate. An explicitly configured field must
be a non-empty dotted path, and its report value must be 64 hexadecimal characters.
Older package versions reject the new contract key; use 0.3+ for digest contracts.
Matching bytes trust the producer's report and do not authenticate source data or
validate artifact content/schema. CSV checks continue to inspect headers, not rows.

## 0.2.0

### Contract and status validation

This release rejects inputs that could previously discard checks or produce a misleading approval:

- Empty report lists, duplicate report names, unknown or duplicate contract fields.
- Non-mapping optional maps, contradictory thresholds, and out-of-range numeric bounds.
- Duplicate report JSON fields, unreadable reports, empty paths, and directory artifacts.
- Packet input with non-boolean decisions, unsupported schema versions or check severities, empty checks, or counts/decisions inconsistent with its checks.

Migration: remove extra keys from contracts, use `{}` rather than `[]` or `null` for optional maps, give reports unique names, and regenerate status files with `validate`. Report objects may still contain extra fields; only contract keys are restricted. CSV checks still inspect headers, not rows.

The CLI also uses the supported `importlib.resources.abc.Traversable` import, avoiding deprecated imports and unexpected stderr on Python 3.12 and removal in Python 3.14.

### Examples and verification

Added a runnable missing-export demonstration, Python 3.11–3.14 CI, lint/format checks, package builds, and an installed-wheel smoke check outside the source checkout.
