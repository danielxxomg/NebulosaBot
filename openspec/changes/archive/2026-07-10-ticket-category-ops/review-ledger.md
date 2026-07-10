# Review Ledger — ticket-category-ops (Judgment Day — design)

**Phase**: post-design  
**Round**: 1  
**Store**: openspec

## Verdict Table

| Finding | Judge A | Judge B | Severity | Assessment | Status |
|---------|---------|---------|----------|------------|--------|
| Edit category bypasses per-user-per-category limit | ✅ JD-A-002 | ✅ JD-B-003 | CRITICAL | — | Fixed (JD-001) |
| Count-then-insert race / double-click not idempotent | ✅ JD-A-001 | ❌ | BLOCKER | — | Fixed (accepted risk) |
| JD-001 exclude mechanism missing from DB count signature | ✅ JD-A (R2) | — | CRITICAL | — | Fixed (R2) |
| JD-A-001 create race not documented in Risks | ✅ JD-A (R2) | — | BLOCKER | — | Fixed (R2) |
| Selector callback lacks staff re-check (300s window) | ✅ JD-A-003 | ❌ | CRITICAL | — | Fixed |
| Spec signature missing channel/actor_id | ❌ | ✅ JD-B-001 | CRITICAL | — | Fixed |
| Spec check_can_edit_category missing is_mod | ❌ | ✅ JD-B-002 | CRITICAL | — | Fixed |
| Service lacks auth boundary (view-only) | ❌ | ✅ JD-B-004 | CRITICAL | — | Fixed |
| Closed ticket edit not specified | ❌ | ✅ JD-B-005 | WARNING | real | Fixed |
| Limit ValueError surfaces generic create-failed UX | ❌ | ✅ JD-B-006 | WARNING | real | Fixed |
| Count query when category_id is None | ❌ | ✅ JD-B-007 | SUGGESTION | — | info |
| Same-category no-op not short-circuited | ❌ | ✅ JD-B-008 | SUGGESTION | — | info |

## Confirmed (both judges)

| id | lens | location | severity | status | evidence |
|----|------|----------|----------|--------|----------|
| JD-001 | judgment-day | design.md + ticket-service/spec.md edit path | CRITICAL | fixed | `edit_ticket_category` now calls `check_one_ticket_per_user_per_category` against the NEW category for the author before DB update, excluding the edited ticket from the count. Round 2: DB count signature `count_user_open_tickets_in_category` gained keyword-only `exclude_ticket_id: str | None = None`; edit path passes `exclude_ticket_id=ticket_id`. design.md Interfaces, prose, ticket-service spec scenario "Same-category no-op edit does not self-block" updated. |

## Suspect (single judge)

| id | severity | status | evidence |
|----|----------|--------|----------|
| JD-A-001 | BLOCKER | fixed (accepted risk) | Round 2: Risks table now documents the app-level count-then-insert race for BOTH create_ticket and edit_ticket_category. Design Risks section documents app-level count-then-insert as accepted risk; AGENTS.md double-click idempotency handled best-effort via UX disable + ephemeral error. No DB unique index (out of scope). |
| JD-A-003 | CRITICAL | fixed | ticket-views spec requires select callback to re-run `is_mod_check()` on submit (300s window); design data flow shows the re-check. |
| JD-B-001 | CRITICAL | fixed | ticket-service spec signature aligned to design: `edit_ticket_category(ticket_id, new_category_id, *, channel, actor_id, is_mod=False) -> tuple[Ticket, bool]`. |
| JD-B-002 | CRITICAL | fixed | ticket-invariants spec updated to `check_can_edit_category(actor_id, ticket, *, is_mod)` matching design and unclaim pattern. |
| JD-B-004 | CRITICAL | fixed | ticket-service spec explicitly mandates `check_can_edit_category(actor_id, ticket, is_mod=is_mod)` BEFORE DB mutation; service is the security boundary. |

## INFO (never block)

See JD-B-005..008 above. JD-B-005 and JD-B-006 fixed (closed-ticket rejection + specific limit UX). JD-B-007/008 remain non-blocking info.

## Judgment

Round 1: confirmed CRITICALs present → not APPROVED. Awaiting fix decision.
Round 2 fix: all confirmed + approved suspects addressed (JD-001, JD-A-001, JD-A-003, JD-B-001..006). Statuses set to fixed. JD-B-007/008 remain non-blocking info. Round 2 surgical: JD-001 exclude mechanism — `count_user_open_tickets_in_category` gained `exclude_ticket_id` keyword-param; design.md Interfaces + prose and ticket-service spec update "Same-category no-op edit does not self-block" scenario added. JD-A-001 create race — Risks table now documents the app-level count-then-insert race for create_ticket as an accepted risk in addition to edit_ticket_category; no migration. Ticket-invariants spec unchanged (pure invariant signature is unaffected; exclusion is a DB method concern).
