# Archive Report: type-strict-core-listeners

**Change**: type-strict-core-listeners
**Archived**: 2026-07-10
**Mode**: openspec
**Verification**: PASS WITH WARNINGS

## Change Summary

Clear all 42 mypy strict errors across `bot.core.*`, `bot.listeners.*`, and `bot.bot` so their three per-file override blocks can be removed from `pyproject.toml`. Zero behavioral change — pure type-safety refactor.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| pyproject-toml-qa-config | Modified | 1 requirement modified ("Mypy configuration present"): updated requirement text, replaced 2 scenarios ("attr-defined suppressed per-file only", "attr-defined still reported in other bot modules") with 4 new scenarios ("Only tech-debt overrides remain", "bot.core passes strict without suppression", "bot.listeners passes strict without suppression", "bot.bot passes strict without suppression"); 1 scenario preserved unchanged ("Mypy strict mode enabled", "bot.models has no type-arg suppression") |

## Archive Contents

- proposal.md ✅
- specs/pyproject-toml-qa-config/spec.md ✅
- design.md ✅
- tasks.md ✅ (17/17 tasks complete)
- verify-report.md ✅
- apply-progress.md ✅
- exploration.md ✅

## Source of Truth Updated

- `openspec/specs/pyproject-toml-qa-config/spec.md` — "Mypy configuration present" requirement updated to reflect surviving overrides-only contract (bot.cogs.* and tests.* only)

## Verification Warnings (non-blocking)

1. Coverage below 80% for 3 changed source files: `bot/core/context.py` (79%), `bot/core/db/infraction_db.py` (71%), `bot/core/db/ticket_category_db.py` (49%). Informational for annotation-focused change.
2. Pre-existing packaging warnings (missing README.md, deprecated setuptools license metadata) — outside this change's diff.
3. Worktree deletes tracked `pyproject.toml.bak` (158 lines) — not listed in proposal/design/tasks/apply-progress changed-file table.

## Task Completion

All 17/17 implementation tasks checked. No stale unchecked tasks.

## SDD Cycle Complete

The change has been fully planned, implemented, verified, and archived. Ready for the next change.
