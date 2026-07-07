# Verification Report: ticket-invariant-layer (B5 full change)

Change: `ticket-invariant-layer`  
Branch: `feat/ticket-invariant-layer-pr3`  
Verified commit: `3a6cbbb`  
Mode: Standard SDD full-change verification across PR1 + PR2 + PR3  
Verifier: SDD `sdd-verify` sub-agent, fresh-context, source inspection plus independent runtime evidence

### Verdict
**PASS**

The B5 ticket invariant layer is archive-ready. The prior P0 task-artifact items are reconciled with honest superseded rationales, migration 005 now enables `pg_cron` before referencing `cron.job`, and the independently executed Python, dashboard, build, migration, and coverage gates completed successfully.

## Runtime Evidence

| Command | Result | Evidence |
|---|---:|---|
| `git checkout feat/ticket-invariant-layer-pr3` | pass | Already on `feat/ticket-invariant-layer-pr3`; local branch contains commit `3a6cbbb`. |
| `uv run pytest` | pass | 742 passed, 3 skipped, 2 warnings in 8.80s. Global bot coverage: 79%, above the 70% threshold. |
| `uv run pytest tests/test_migrations.py` | pass | 34 migration tests passed in 0.30s, including migration 005 checks. |
| `cd dashboard && npm test` | pass | 234 passed across 15 files in 1.60s. The contract suite contributed 42 passing tests. |
| `cd dashboard && npm run build` | pass | Next.js 15.5.19 production build compiled, type-checked, generated static pages, and collected traces successfully. |

Notes on runtime signal: pytest still emits two pre-existing `AsyncMock` warnings, and Vitest still emits React `act(...)` warnings in `tickets-page.test.tsx`. These are quality follow-ups, not archive blockers for B5 behavior.

## Completeness Table

| Dimension | Status | Notes |
|---|---|---|
| Proposal / scope | Covered | The six scoped drifts are addressed: permissions, reopen guidance, transfer status, note cap/ownership/dedup, audit trail, and mirrored contract coverage. |
| Specs | Covered | Ticket invariants, service, views, and dashboard deltas have implementation evidence and runtime tests in the correct domain. |
| Design | Covered | Python service invariants, TS mirror, Discord-side effects, dashboard guidance-only reopen, app-level dedup, and audit storage match the design. |
| Tasks | Covered | `tasks.md` now has 57 checked tasks and 0 unchecked tasks. Tasks 2.10, 2.12, and 2.19 are checked with explicit superseded rationale. |
| Migration | Covered | `migrations/005_ticket_audit.sql` includes `CREATE EXTENSION IF NOT EXISTS pg_cron;` before the guarded `cron.job` lookup. |
| Runtime | Covered | Bot tests, dashboard tests, dashboard build, targeted migration tests, and global coverage all executed independently. |
| Archive readiness | Ready | No open SDD verification blockers remain for this change. |

## Fix Re-assessment

| Item | Assessment | Evidence |
|---|---|---|
| P0 task reconciliation | Resolved | `openspec/changes/ticket-invariant-layer/tasks.md` lines 48, 50, and 57 now mark 2.10, 2.12, and 2.19 as checked with explicit superseded rationale. A task parse found 57 checked tasks and 0 unchecked tasks. |
| Task 2.10 superseded rationale | Honest | Audit reasons are inlined at call sites in `bot/services/ticket_service.py`; audit insert/read methods are guild-scoped through `bot/core/database.py` `.eq("guildId", ...)`. The intent is implemented without a separate `build_audit_reason()` helper. |
| Task 2.12 superseded rationale | Honest | Button and command permissions use `is_mod_check()` plus author checks in `bot/cogs/tickets.py`; pure invariant checks live in `bot/services/ticket_invariants.py`. The intent is implemented without a centralized `PERMISSION_MATRIX` dict. |
| Task 2.19 superseded rationale | Honest | `dashboard/__tests__/contract/ticket-invariants.test.ts` contains enabled TI-001..TI-038 tests, and `npm test` reports the dashboard contract suite passing 42 tests. This exceeds the original skip-stub task. |
| P1.2 migration self-containment | Resolved | `migrations/005_ticket_audit.sql:80` creates `pg_cron` idempotently before the DO block queries `cron.job` and calls `cron.schedule`. Targeted migration tests passed. |
| P1.1 Python dashboard skips | Acceptable | TI-028, TI-030, and TI-038 are dashboard scenarios: audit view admin-only, no-category dashboard guidance error, and paginated audit display. The Python suite cannot exercise TS dashboard UI/server-action behavior directly; Vitest covers these rows and passed. Interpreting “both suites mirror every row” as domain-aware mirroring is correct here: bot-testable rows in pytest, dashboard-testable rows in Vitest, shared pure invariants in both. |

## Spec Compliance Matrix

| Spec | Requirement group | Runtime coverage | Result |
|---|---|---|---|
| `ticket-invariants` | Status transitions, invalid transition rejection, transfer status normalization | Pytest TI-001..TI-010; Vitest TI-001..TI-010 | ✅ COMPLIANT |
| `ticket-invariants` | parentId invariants: existence, same guild, not self, depth max 2 | Pytest TI-011..TI-015; Vitest TI-011..TI-015 | ✅ COMPLIANT |
| `ticket-invariants` | Note dedup and idempotency rules | Pytest TI-016..TI-018; Vitest TI-016..TI-018 | ✅ COMPLIANT |
| `ticket-invariants` | Audit success, denied outcomes, guild-scoped reads | Pytest TI-019..TI-021; Vitest TI-019..TI-021 | ✅ COMPLIANT |
| `ticket-invariants` | Permission matrix and documented dashboard admin-only divergence | Pytest TI-022..TI-027 plus Vitest TI-022..TI-028 | ✅ COMPLIANT |
| `ticket-views` | Claim and close button gates; `/reopen` ticket ref and legacy no-arg path | Pytest TI-023, TI-024, TI-029, TI-036, TI-037 plus cog/service tests | ✅ COMPLIANT |
| `ticket-service` | Transfer, claim no-overwrite, note dedup, and audit rows | Pytest contract and service tests in `uv run pytest` | ✅ COMPLIANT |
| `dashboard-ticket-view` | Reopen guidance, category gate, transfer status, notes cap/ownership, audit view | Vitest TI-029..TI-038 plus action/UI tests | ✅ COMPLIANT |

Compliance summary: all B5 behavioral requirement groups are covered by passing runtime tests in their executable domain.

## Design Coherence

| Design decision | Followed | Evidence |
|---|---:|---|
| Python invariant layer plus TS mirror, no runtime code sharing | Yes | `bot/services/ticket_invariants.py`, `dashboard/lib/ticket-invariants.ts`, and dashboard server helpers are present and covered. |
| Contract scenario IDs are reviewable in both suites | Yes | Python keeps the shared/bot rows executable and documents dashboard-only rows; dashboard has enabled TI-001..TI-038 coverage. |
| Dashboard reopen guidance only, bot creates channels | Yes | Dashboard returns `/reopen ticket:#NNNN` guidance without DB status mutation; bot `/reopen` resolves ticket refs and owns channel creation. |
| Category gate before dashboard guidance | Yes | Missing `ticketCategoryId` produces an error path covered by Vitest TI-030. |
| App-level note dedup with no `contentHash` schema column | Yes | Dedup helpers and recent-note query are app-level; migration adds only the supporting note index. |
| Audit table, RLS, service-role guild filters, retention | Yes | Migration creates audit storage/indexes/RLS and `pg_cron`; Python and dashboard audit queries filter by guild. |
| Button permissions use `is_mod_check()` predicate, not UI decorator misuse | Yes | `bot/utils/checks.py` exposes the predicate; button callbacks gate inline. |

## Decision Coverage

| Decision | Status | Evidence |
|---|---|---|
| Keep bot commands on `@is_mod()` while dashboard remains admin-only | Covered | Bot uses `is_mod_check()`/decorator path; dashboard actions authorize admin context. |
| Claim overwrite is denied | Covered | Python invariant and service tests cover already-claimed and same-user claim denial. |
| Bot keeps new-channel reopen; dashboard avoids zombie DB flip | Covered | Bot service owns reopen channel creation; dashboard guidance path is no-mutation. |
| Transfer sets `claimedBy` and `status='claimed'` on both sides | Covered | Python service and dashboard action tests cover status normalization. |
| Legacy claimed/open rows normalized in migration 005 | Covered | Migration backup plus update are present and migration tests pass. |
| Dashboard notes enforce cap 50 and author-only delete | Covered | Dashboard action/UI tests and Vitest contract rows cover both behaviors. |
| Dedup hash formula is mirrored | Covered | Python and TS helpers normalize whitespace/case and hash with SHA256. |
| Audit trail table, indexes, guild scope, and retention | Covered | Migration 005, DB methods, dashboard action, and tests cover storage and reads. |

## Follow-up Notes

| Priority | Note | Recommendation |
|---|---|---|
| P2 | `bot/services/ticket_service.py` still has stale transfer docstring text saying no DB audit row, while the implementation now writes one. | Clean the docstring in a small later docs/code-quality pass. |
| P2 | Test suites emit warning noise: pytest `AsyncMock` runtime warnings and Vitest React `act(...)` warnings. | Track separately to improve test signal; not part of B5 archive gating. |

## Archive Readiness

`ticket-invariant-layer` is ready for `sdd-archive`. The source artifacts, tasks, migration, runtime evidence, and domain-aware contract coverage are consistent enough to promote the delta specs.
