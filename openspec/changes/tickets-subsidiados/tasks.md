# Tasks: Tickets Subsidiados

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~940 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: stacked-to-main|feature-branch-chain|size-exception|pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Schema + Models + Database | PR 1 | `feature/tickets-subsidiados-pr1` base; migration, Ticket.parent_id, TicketNote model, DB CRUD methods + all tests |
| 2 | Bot service + cog commands | PR 2 | `feature/tickets-subsidiados-pr2` base = PR 1 branch; service layer (create_subticket/reopen/transfer/notes) + slash commands + all tests |
| 3 | Dashboard types + actions + UI | PR 3 | `feature/tickets-subsidiados-pr3` base = PR 2 branch; TS types, server actions, RSC tree, client components + all tests |

---

## Phase 1: Migration & Schema

- [ ] 1.1 **RED** — Write `tests/test_migrations.py`: test Migration 003 on existing data keeps `parentId=null` for existing tickets, `ticket_note` table exists with columns `id/ticketId/authorId/content/createdAt`, 3 indexes exist. `uv run pytest tests/test_migrations.py` must FAIL (no migration file yet).
- [ ] 1.2 **GREEN** — Create `migrations/003_subtickets_notes.sql` with exact DDL from design.md: `ALTER TABLE ticket ADD COLUMN IF NOT EXISTS "parentId" UUID;` + `CREATE TABLE IF NOT EXISTS ticket_note (...)` + 3 indexes. `uv run pytest tests/test_migrations.py` must PASS.
- [ ] 1.3 **VERIFY** — Apply migration to Supabase dev instance. `uv run pytest tests/test_migrations.py -v` green. Existing tickets unaffected.

## Phase 2: Models

- [ ] 2.1 **RED** — Write `tests/test_ticket_model.py`: test `Ticket.from_db_row` maps `parentId` → `parent_id`; `to_db_dict` includes `"parentId"`. Test both null and populated cases. Must FAIL.
- [ ] 2.2 **GREEN** — Modify `bot/models/ticket.py`: add `parent_id: str | None = None` field; update `from_db_row`/`to_db_dict` to map `parentId`↔`parent_id`. Must PASS.
- [ ] 2.3 **RED** — In same test file: test `TicketNote.from_db_row` maps camelCase DB keys → snake_case attrs; `to_db_dict` converts back. Must FAIL.
- [ ] 2.4 **GREEN** — Create `bot/models/ticket_note.py`: `TicketNote(id, ticket_id, author_id, content, created_at)` dataclass with `from_db_row`/`to_db_dict`. Must PASS.
- [ ] 2.5 **VERIFY** — `uv run pytest tests/test_ticket_model.py -v` all green.

## Phase 3: Database

- [ ] 3.1 **RED** — Write `tests/test_database.py` additions: test `insert_ticket(..., parent_id="uuid")` stores parentId; `get_tickets_by_parent(parent_id)` returns children only. Must FAIL.
- [ ] 3.2 **GREEN** — Modify `bot/core/database.py`: extend `insert_ticket` with optional `parent_id` param; add `get_tickets_by_parent`. Must PASS.
- [ ] 3.3 **RED** — Test `insert_ticket_note`, `get_ticket_notes` (ordered newest-first, capped by caller), `delete_ticket_note`. Must FAIL.
- [ ] 3.4 **GREEN** — Add `insert_ticket_note`, `get_ticket_notes`, `delete_ticket_note` to `database.py`. Must PASS.
- [ ] 3.5 **VERIFY** — `uv run pytest tests/test_database.py -v` all green.

## Phase 4: Service Layer (CRITICAL)

- [ ] 4.1 **RED** — Write `tests/test_ticket_service.py`: 4 FK rejection tests — parent not found raises `ValueError`, self-reference rejected, sub-of-sub rejected, cross-guild rejected. Must FAIL.
- [ ] 4.2 **GREEN** — Implement `create_subticket` in `bot/services/ticket_service.py` with all 4 FK validations + parent_id pass-through. Must PASS.
- [ ] 4.3 **RED** — Test valid sub-ticket creation succeeds; test duplicate check carve-out (parentId set → skip one-open-ticket constraint). Must FAIL.
- [ ] 4.4 **GREEN** — Wire carve-out into `create_ticket`/`create_subticket` flow. Must PASS.
- [ ] 4.5 **RED** — Test `reopen_ticket`: new channel created, `channelId` updated, `status=open`, `closedAt=null`, `_ticket_channel_cache.add` called. Test category-deleted fallback to default. Must FAIL.
- [ ] 4.6 **GREEN** — Implement `reopen_ticket` with category fallback + cache update. Must PASS.
- [ ] 4.7 **RED** — Test `transfer_ticket`: `claimedBy` mutated, `LoggingService` audit embed called with actor+target+ticket info. Test unclaimed→claimed. Must FAIL.
- [ ] 4.8 **GREEN** — Implement `transfer_ticket` calling `LoggingService` after mutation. Must PASS.
- [ ] 4.9 **RED** — Test note CRUD: `create_note` inserts row, `get_notes` returns list, `delete_note` by owner succeeds, delete by non-owner raises, cap at 50 raises. Must FAIL.
- [ ] 4.10 **GREEN** — Implement note CRUD in service layer with cap enforcement + ownership check. Must PASS.
- [ ] 4.11 **VERIFY** — `uv run pytest tests/test_ticket_service.py -v` all green.

## Phase 5: Cog Commands

- [ ] 5.1 **RED** — Write `tests/test_tickets_cog.py`: test `/subticket create` (gated by `@is_mod()`), `/reopen`, `/transfer @user`, `/note add`, `/note list`, `/note delete`. Mock service calls, verify permission gating. Must FAIL.
- [ ] 5.2 **GREEN** — Modify `bot/cogs/tickets.py`: add `subticket` hybrid group + `reopen`, `transfer`, `note add/list/delete` hybrid commands, all `@is_mod()`. Must PASS.
- [ ] 5.3 **VERIFY** — `uv run pytest tests/test_tickets_cog.py -v` all green.

## Phase 6: Dashboard Types & Actions

- [ ] 6.1 **RED** — Write `dashboard/__tests__/lib/actions/ticket-actions.test.ts`: test `reopenTicket`, `transferTicket`, `getTicketNotes`, `addTicketNote`, `deleteTicketNote` call `verifyGuildAdmin` before mutation. Must FAIL.
- [ ] 6.2 **GREEN** — Modify `dashboard/lib/types.ts`: add `parentId?: string` to `Ticket`, add `TicketNote` interface. Modify `dashboard/lib/actions/ticket-actions.ts`: add all 5 actions with `verifyGuildAdmin` guard. Must PASS.
- [ ] 6.3 **VERIFY** — `cd dashboard && npm test` all green.

## Phase 7: Dashboard UI

- [ ] 7.1 **RED** — Write `dashboard/__tests__/app/tickets-page.test.tsx`: test parent→child tree render (children indented), orphan fallback to top-level, action buttons (Reopen on closed only, Transfer on claimed, Notes always), notes panel empty/add/list states, non-admin sees no buttons. Must FAIL.
- [ ] 7.2 **GREEN** — Modify `dashboard/app/(authenticated)/guilds/[guildId]/tickets/page.tsx`: build parent→child tree in RSC. Create `_components/TicketRowActions.tsx`, `_components/NotesPanel.tsx` as `'use client'` components. Apply frontend-design/impeccable principles: accessible labels, disabled/loading states, empty notes state "No staff notes yet.", no nested cards. Must PASS.
- [ ] 7.3 **VERIFY** — `cd dashboard && npm test` all green. `cd dashboard && npm run build` no errors.

## Phase 8: Full Verification

- [ ] 8.1 **VERIFY** — `uv run pytest` all bot tests green, no regressions.
- [ ] 8.2 **VERIFY** — `cd dashboard && npm test` all dashboard tests green.
- [ ] 8.3 **VERIFY** — `cd dashboard && npm run build` production build succeeds.
- [ ] 8.4 **VERIFY** — Manual spot-check: migration applied, sub-ticket creates, reopen works, transfer logs, notes CRUD functional.

## Phase 9: Commit Strategy

- [ ] 9.1 NO commit here — orchestrator runs `review-reliability` then handles commit/PR strategy. This change is >400 lines → `ask-on-risk` will prompt user to choose: single `size:exception` OR chained PRs (recommended: PR1 schema+models+DB, PR2 service+cog, PR3 dashboard).
