# Archive Report: ticket-invariant-layer

## Change Summary

| Field | Value |
|-------|-------|
| Change name | ticket-invariant-layer |
| Branch | feat/ticket-invariant-layer-pr3 |
| Status | **archived PASS** |
| Verified commit | 3a6cbbb |
| Archived date | 2026-07-06 |
| PRs | #12, #13, #14 (feature-branch-chain) |

## Test Results

| Suite | Result | Details |
|-------|--------|---------|
| Bot (pytest) | 742 passed, 3 skipped | 8.80s, 79% coverage (above 70% threshold) |
| Dashboard (vitest) | 234 passed | 15 files, 1.60s, 42 contract tests |
| Dashboard build | Clean | Next.js 15.5.19 production build |
| Migration tests | 34 passed | 0.30s, migration 005 checks included |

## Decision Coverage

13 decisions tracked and verified:

| Decision | Status |
|----------|--------|
| Keep bot commands on @is_mod() while dashboard remains admin-only | Covered |
| Claim overwrite is denied | Covered |
| Bot keeps new-channel reopen; dashboard avoids zombie DB flip | Covered |
| Transfer sets claimedBy and status='claimed' on both sides | Covered |
| Legacy claimed/open rows normalized in migration 005 | Covered |
| Dashboard notes enforce cap 50 and author-only delete | Covered |
| Dedup hash formula is mirrored | Covered |
| Audit trail table, indexes, guild scope, and retention | Covered |
| Dashboard category gate before guidance | Covered |
| Button permissions use is_mod_check() predicate | Covered |
| App-level note dedup with no contentHash schema column | Covered |
| Contract scenario IDs are reviewable in both suites | Covered |
| Dashboard reopen guidance only, bot creates channels | Covered |

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| ticket-invariants | Verified (already current) | NEW capability — 6 requirements, 38 scenarios. PR1 created it; verified identical to change spec. |
| ticket-service | Updated | MODIFIED: transfer_ticket (status='claimed' + audit), Ticket claim (no-overwrite + same-user reject). ADDED: Note dedup enforcement, Audit logging on ticket operations. |
| ticket-views | Updated | MODIFIED: Ticket actions view (Claim @is_mod gate, Close author OR mod gate). ADDED: Reopen command accepts ticket-id. |
| dashboard-ticket-view | Updated | MODIFIED: Reopen action (guidance modal, no mutation), Transfer action (status update). ADDED: Notes cap enforcement, Notes delete author-only, Audit view. |

## Archive Contents

- proposal.md ✅
- specs/ ✅ (ticket-invariants, ticket-service, ticket-views, dashboard-ticket-view)
- design.md ✅
- tasks.md ✅ (57/57 tasks complete)
- verify-report.md ✅ (PASS)

## Source of Truth Updated

The following main specs now reflect the new behavior:

- `openspec/specs/ticket-invariants/spec.md` — verified current (NEW capability)
- `openspec/specs/ticket-service/spec.md` — synced with delta (transfer status, claim no-overwrite, note dedup, audit)
- `openspec/specs/ticket-views/spec.md` — synced with delta (button gates, /reopen ticket-id)
- `openspec/specs/dashboard-ticket-view/spec.md` — synced with delta (reopen guidance, transfer status, notes cap/ownership, audit view)

## Engram Artifacts

| Artifact | Observation ID |
|----------|---------------|
| sdd/ticket-invariant-layer/decisions | #669 |
| sdd/ticket-invariant-layer/apply-progress | #674 |
| sdd/ticket-invariant-layer/archive-report | (this save) |

## Follow-up Notes

| Priority | Note | Recommendation |
|----------|------|----------------|
| P2 | `bot/services/ticket_service.py` stale transfer docstring text (says no DB audit row, but implementation writes one) | Clean in a docs/code-quality pass |
| P2 | Test warning noise: pytest AsyncMock warnings, Vitest React act(...) warnings | Track separately |
| P3 | ReopenTicketDialog showModal a11y — no focus trap or Escape key handler | Accessibility improvement |
| P3 | React act() warnings in tickets-page.test.tsx | Wrap async state updates in act() |
| P3 | Debt #545 — existing technical debt item | Track in backlog |
| P3 | Coverage gaps in edge cases | Expand test coverage incrementally |
| P3 | Live CDC end-to-end verification needs Pterodactyl staging environment | Deferred — requires infra setup |

## SDD Cycle Complete

The ticket-invariant-layer change has been fully planned, implemented, verified, and archived.
All 6 drifts resolved: bot + dashboard enforce identical invariants.
Mirrored contract tests pass on both sides (pytest + vitest).
Ready for the next change.
