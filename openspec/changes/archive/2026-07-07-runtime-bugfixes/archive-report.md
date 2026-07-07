# Archive Report: Runtime Bugfixes

**Change**: `runtime-bugfixes`
**Archived**: 2026-07-07
**Archived to**: `openspec/changes/archive/2026-07-07-runtime-bugfixes/`
**Mode**: openspec
**Verification verdict**: PASS WITH WARNINGS (no CRITICAL issues)

---

## Task Completion Gate

Task 5.1 was unchecked in `tasks.md` but explicitly deferred to archive phase ("done by archive phase"). Reconciliation reason: archive Step 2 (sync delta specs to main specs) IS task 5.1. The `verify-report` confirms 18/19 tasks complete with 5.1 as archive-only. Marked 5.1 as `[x]` in archived tasks.md.

Final task count: **19/19 complete**.

---

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| `initial-schema` | Updated | 1 removed (User table), 4 modified (Migration 001, Member table, Infraction table, Ticket table) |
| `cache-sync-realtime` | Updated | 1 added (Payload table resolution), 2 modified (Reconnection and health check, Migration prerequisite — watchdog event counting) |
| `ocio-commands` | Updated | 1 modified (Banana command — WebP asset path) |

### initial-schema — Removed Requirements

| Requirement | Reason | Migration |
|-------------|--------|-----------|
| User table | Vestigial — bot never writes to it, dashboard specs do not reference it. All 4 FK constraints referencing `user(id)` are dropped in Migration 006. | Remove any code or tests that insert/query the `user` table. `member.userId`, `infraction.targetId`, `infraction.moderatorId`, `ticket.authorId` columns retained as plain strings without FK enforcement. |

### initial-schema — Preserved Requirements (not in delta)

Guild table, Migration 002, Ticket category table, Ticket category indexes, Migration 003, parentId column, ticket_note table, ticket_note index — all preserved unchanged.

### cache-sync-realtime — Preserved Requirements (not in delta)

Realtime subscriber lifecycle, Cache invalidation on CDC events, Poll fallback, Self-echo filtering — all preserved unchanged.

---

## Archive Contents

- `proposal.md` ✅
- `specs/initial-schema/spec.md` ✅
- `specs/cache-sync-realtime/spec.md` ✅
- `specs/ocio-commands/spec.md` ✅
- `design.md` ✅
- `tasks.md` ✅ (19/19 tasks complete)
- `verify-report.md` ✅

## Source of Truth Updated

The following main specs now reflect the new behavior:

- `openspec/specs/initial-schema/spec.md` — User table removed, FK references removed from Member/Infraction/Ticket, Migration 001 wording updated
- `openspec/specs/cache-sync-realtime/spec.md` — Payload table resolution added, Reconnection health check enhanced with close logging and escalation, Migration prerequisite updated with watchdog received-count semantics
- `openspec/specs/ocio-commands/spec.md` — Banana command updated to use `assets/images/banana.webp`

## Non-blocking Warnings (carried from verify-report)

1. Live DB execution not performed — migration final state verified by static SQL artifact tests only
2. Remediation TDD order cannot be independently proven — no separate remediation apply-progress artifact records RED-before-GREEN ordering

## SDD Cycle Complete

The change has been fully planned, implemented, verified, and archived. Ready for the next change.
