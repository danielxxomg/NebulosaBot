# Specs — Code Quality Consolidation

**Status**: No delta specs — this change has zero behavioral requirements.

## Reason

This is a pure refactor + infrastructure change:

- **Constant extraction**: Moving `"nb!"` to a shared `bot/constants.py` — no behavior change
- **Dedup helper**: Removing duplicate `_resolve_avatar_url` from cog — function already exists in service
- **CI tooling**: Adding jscpd + vulture as report-only — no enforcement, no behavior change
- **Git hygiene**: Deleting merged branches and stale stashes — repo cleanup, no code change

All work is internal restructuring. User-facing behavior, commands, events, and data flow remain identical. The `sdd-design` phase will produce an architecture-level technical plan (file changes, import updates, CI workflow) without needing spec requirements to drive it.

## Verification (by success criteria, not specs)

Success is measured by concrete, testable outcomes from the proposal:

| Criterion | How to Verify |
|-----------|---------------|
| `"nb!"` in 1 file | `grep -r '"nb!"' bot/` returns only `constants.py` |
| `_resolve_avatar_url` in 1 file | `grep -r '_resolve_avatar_url' bot/` returns only `greeting_service.py` |
| Tests pass | `uv run pytest` — 957+ tests, ≥ 75% coverage |
| CI runs | GitHub Actions workflow shows jscpd + vulture steps green (report-only) |
| Branches cleaned | `git branch -r` shows no merged stale branches |
