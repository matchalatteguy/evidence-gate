# Changelog

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
