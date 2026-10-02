# Contributing

Thanks for considering a contribution.

## Development setup

This project uses Python, `uv`, `pytest`, and `ruff`.

```bash
uv sync --locked --dev
uv run ruff check .
uv run ruff format --check .
uv run pytest -W error::DeprecationWarning
uv build
```

## Pull requests

Before opening a pull request, please:

- keep changes focused and easy to review;
- add or update tests for behavior changes;
- update docs or examples when public behavior changes;
- run the local checks above;
- avoid committing local caches, generated build outputs, secrets, credentials, or machine-specific paths.

## Project scope

Keep the package generic and reusable. Avoid domain-specific private context, organization-specific assumptions, and hardcoded local paths.

Evidence Gate is a declarative local gate. Keep producer computations outside the
validator, preserve exit-code and failure-code semantics, and state what each check
actually establishes. New artifact checks should stream when possible and retain
bounded diagnostics. Reference comparisons must fail closed for missing context
or unsupported values. Update the contract reference and migration notes when
introducing new keys or numeric/path policies.
