# Archive Report: Type-Strict Cogs

**Change**: `type-strict-cogs`
**Archived**: 2026-07-10
**Mode**: openspec
**Verdict**: PASS WITH WARNINGS (no CRITICAL)

## Summary

Narrowed the blanket `bot.cogs.*` mypy override from 7 suppressed error codes to only `untyped-decorator`. Fixed 62 type errors across 9 cog files: parameterized `Context[Any]`, narrowed `discord.Member` contracts, guarded nullable Discord fields, removed stale `# type: ignore[override]` comments, and added 25 inline `arg-type` suppressions for discord.py hybrid_command stub limitations. Full mypy and pytest verification passed.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| N/A | None | No delta specs — pure type-safety refactor with no behavioral requirements |

## Archive Contents

- proposal.md ✅
- exploration.md ✅
- design.md ✅
- tasks.md ✅ (18/18 tasks complete)
- verify-report.md ✅
- apply-progress.md ✅
- archive-report.md ✅ (this file)

## Verification Summary

| Check | Result |
|-------|--------|
| `uv run mypy bot/cogs` | ✅ Zero errors (9 files) |
| `uv run mypy bot` | ✅ Zero errors (65 files) |
| `uv run pytest` | ✅ 1429 passed, 3 skipped, 87.95% coverage |
| `TestMypyCogsOverride` | ✅ 2/2 passed |
| All 18 tasks complete | ✅ No stale checkboxes |
| CRITICAL issues | ✅ None |

## Warnings (non-blocking)

1. Ruff: 9 import-order errors + 1 line-length error in `sentinel.py` (follow-up needed)
2. `sentinel.py` (77%) and `setup.py` (76%) below 80% changed-file coverage guideline
3. Historical RED evidence for annotation-only work is N/A (static harness)
4. Narrowed pytest selection needs `--no-cov` for project-wide coverage gate

## Source of Truth Updated

No main specs were modified — this change has no delta spec artifacts.

## SDD Cycle Complete

The change has been fully planned, implemented, verified, and archived.
Ready for the next change.
