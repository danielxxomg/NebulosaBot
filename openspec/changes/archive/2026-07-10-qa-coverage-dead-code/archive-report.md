# Archive Report: qa-coverage-dead-code

**Change**: `qa-coverage-dead-code`
**Archived**: 2026-07-10
**Mode**: openspec
**Verdict**: PASS WITH WARNINGS

## Summary

QA coverage and dead code cleanup — added contract tests for brand tokens, docs manual discovery, DB facades, help builder, model round-trips, and sentinel behavior. Fixed guild-scoped DB facade signatures and Member datetime parsing. 24/24 tasks complete across 3 stacked PRs. 1334 tests passing, 87.39% coverage.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| brand-tokens | Updated | 1 requirement added (Brand token contract tests) |
| docs-manual | Updated | 1 requirement added (Dynamic hybrid command discovery test) |
| qa-db-facade-coverage | Created | New spec — 4 requirements (TicketCategoryDB, TicketDB, GreetingDB, InfractionDB facade coverage) |
| qa-help-builder | Created | New spec — 3 requirements (embed builder, help pages, prefix resolution) |
| qa-model-coverage | Created | New spec — 2 requirements (EconomyConfig round-trip, Member round-trip with datetime) |
| qa-sentinel-behavior | Created | New spec — 4 requirements (warn, mute, kick/ban confirmation, validate_target) |

## Archive Contents

- proposal.md ✅
- exploration.md ✅
- specs/ (6 domains) ✅
- design.md ✅
- tasks.md ✅ (24/24 tasks complete)
- apply-progress.md ✅
- verify-report.md ✅

## Source of Truth Updated

- `openspec/specs/brand-tokens/spec.md` — merged ADDED requirement
- `openspec/specs/docs-manual/spec.md` — merged ADDED requirement
- `openspec/specs/qa-db-facade-coverage/spec.md` — created
- `openspec/specs/qa-help-builder/spec.md` — created
- `openspec/specs/qa-model-coverage/spec.md` — created
- `openspec/specs/qa-sentinel-behavior/spec.md` — created

## Warnings (non-blocking)

1. `apply-progress.md` maps only 13/24 original tasks to direct TDD evidence.
2. `ticket_category_db.py` (49%) and `infraction_db.py` (71%) below Strict-TDD 80% advisory; changed lines are covered.
3. `TestGetOpenTicketChannelIds` uses 3 IDs vs spec's 4; behavior covered.
4. Proposal rollback says zero production changes, but design/implementation correctly includes 8 production files.
5. `uv run ruff check .` has 64 inherited/non-change violations; none on this change's lines.

## SDD Cycle Complete

The change has been fully planned, implemented, verified, and archived.
Ready for the next change.
