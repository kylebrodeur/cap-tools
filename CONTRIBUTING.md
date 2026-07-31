# Contributing

## Dev setup

```bash
uv sync
uv run pytest tests/ -v
```

That's the whole loop — no separate lint/build step. macOS-only tests (anything touching `capt.record.macos_capture`) skip themselves automatically on other platforms.

## Making a change

1. Open an issue first for anything beyond a small fix, so we can agree on direction before you invest time.
2. Keep PRs scoped to one change. Add or update tests for anything you touch — see `tests/` for the existing style (mock subprocess/Playwright boundaries, assert on real behavior).
3. Run the full suite before opening the PR: `uv run pytest tests/ -v`.

## Reporting a bug

Include your platform (macOS/Linux/WSL), the exact `capt` command, and the full output of `capt preflight`. If it's a `capt guide`/`capt assemble` issue, note whether `--ai` was involved.
