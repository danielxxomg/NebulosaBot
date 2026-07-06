# Tasks: Ticket Invariant Layer

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1870 (bot ~1070 + dashboard ~800 + migration ~60) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 |
| Delivery strategy | auto-forecast |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Audit infrastructure + shared invariant module + contract tests | PR 1 | Base: `main`. Migration 005, database CRUD, `ticket_invariants.py`, TI-001→TI-038 pytest, TI-001→TI-038 vitest stubs. Independently green. |
| 2 | Bot service/cog integration + integration tests | PR 2 | Base: PR 1 branch. Wire invariants into `ticket_service.py` + `tickets.py`. Service integration tests. Independently green. |
| 3 | Dashboard invariant mirror + drift fixes + UI + contract tests | PR 3 | Base: PR 2 branch. TS mirror, guidance modal, notes cap/ownership, audit panel. Dashboard contract tests. Likely ~800 lines → `size:exception`. |

---

## Phase 1: Audit Infrastructure (PR 1)

- [x] 1.1 RED: write failing test `test_ti019_audit_success_insert` in `tests/contract/test_ticket_invariants.py` asserting `insert_audit_row()` persists a row with outcome=success
- [x] 1.2 GREEN: create `migrations/005_ticket_audit.sql` — `ticket_audit` table (id UUID PK, guildId TEXT, ticketId UUID, action TEXT, actorId TEXT, outcome TEXT CHECK, reason TEXT, createdAt TIMESTAMPTZ), indexes (ticket_history, guild_created, guild_action), `ticket_note` author+created index, RLS enabled, transfer normalization UPDATE with idempotent backup
- [x] 1.3 RED: write failing tests for `get_ticket_by_number`, `insert_audit_row`, `get_audit_rows` in `tests/test_database.py`
- [x] 1.4 GREEN: add to `bot/core/database.py` — `get_ticket_by_number(guild_id, ticket_number)` using `.eq("guildId").eq("ticketNumber")`; `insert_audit_row(guild_id, ticket_id, action, actor_id, outcome, reason)`; `get_audit_rows(guild_id, limit, offset)` ordered by createdAt DESC; `get_recent_notes_for_dedup(ticket_id, author_id, since_iso)` filtered by authorId+createdAt>=since
- [x] 1.5 REFACTOR: extract `_AUDIT_COLUMNS` constant if repeated across audit methods

## Phase 2: Invariant Module + Contract Tests (PR 1)

- [ ] 2.1 RED: write failing tests TI-001→TI-007 (status state machine + claim no-overwrite) in `tests/contract/test_ticket_invariants.py`
- [ ] 2.2 GREEN: create `bot/services/ticket_invariants.py` — `validate_status_transition(current, action)` raises ValueError on invalid; `validate_claim(ticket_row)` raises if claimedBy set; `check_actor_permission(actor_roles, action)` returns bool per permission matrix
- [ ] 2.3 RED: write failing tests TI-008→TI-010 (transfer invariants: open→claimed, reassign, same-user denied)
- [ ] 2.4 GREEN: add `validate_transfer(ticket_row, new_claimed_by)` raises if same user
- [ ] 2.5 RED: write failing tests TI-011→TI-015 (parentId invariants: valid, missing, self, depth, cross-guild)
- [ ] 2.6 GREEN: add `validate_parent_id(parent_row, child_guild_id, child_id)` raises ValueError with reason
- [ ] 2.7 RED: write failing tests TI-016→TI-018 (note dedup: exact hash denied, outside window allowed, different author allowed)
- [ ] 2.8 GREEN: add `compute_dedup_hash(content)` returning SHA256 of normalized content; `check_note_dedup(recent_notes, content, author_id)` raises ValueError on duplicate within 2s
- [ ] 2.9 RED: write failing tests TI-020→TI-021 (audit violations + guild scope)
- [ ] 2.10 GREEN: add `build_audit_reason(action, outcome, detail)` helper; ensure guild scope via `.eq("guildId")` in database methods
- [ ] 2.11 RED: write failing tests TI-022→TI-028 (permission matrix: create any, claim mod, close author+mod, reopen mod, transfer admin, notes/staff admin+mod, audit view admin)
- [ ] 2.12 GREEN: add `PERMISSION_MATRIX` dict mapping action→allowed roles; update `check_actor_permission` to consult it
- [ ] 2.13 RED: write failing tests TI-029→TI-030 (drift: reopen by number, no category error)
- [ ] 2.14 GREEN: add `parse_ticket_ref(ref_str)` parsing `#0003`, `0003`, UUID, stripping `ticket:` prefix
- [ ] 2.15 RED: write failing tests TI-031→TI-035 (note cap, delete ownership, under cap, author delete own)
- [ ] 2.16 GREEN: add `validate_note_cap(note_count)` raises at 50; `validate_note_delete(note_row, actor_id)` raises if not owner
- [ ] 2.17 RED: write failing test TI-033 (guild scope — ticket/note/audit from guild B not leakable from guild A)
- [ ] 2.18 RED: write failing tests TI-036→TI-038 (action view render, no-arg legacy reopen, audit paginated)
- [ ] 2.19 GREEN: stub dashboard-side assertions as vitest `describe.skip` blocks in `dashboard/__tests__/contract/ticket-invariants.test.ts` — one test per ScenarioID with correct function name (e.g. `ti001OpenToClaimed`), asserting the pure TS invariant or marking as bot-only
- [ ] 2.20 REFACTOR: deduplicate fixture factories (mock ticket rows, mock guild config, mock interaction) across contract test file

## Phase 3: Bot Service/Cog Integration (PR 2)

- [ ] 3.1 RED: write failing test `test_claim_audits_success` asserting `claim_ticket` writes audit row with outcome=success
- [ ] 3.2 GREEN: in `bot/services/ticket_service.py` `claim_ticket()` — call `validate_claim()` from invariants BEFORE `update_ticket`; call `insert_audit_row()` after; catch ValueError → audit denied + re-raise
- [ ] 3.3 RED: write failing test `test_transfer_same_user_denied` asserting `transfer_ticket(ticket, userA, userA)` raises ValueError
- [ ] 3.4 GREEN: in `transfer_ticket()` — add `if claimed_by == new_claimed_by: raise ValueError("same user")`; audit success/denied
- [ ] 3.5 RED: write failing test `test_note_dedup_within_window` asserting `create_note()` raises ValueError for duplicate within 2s
- [ ] 3.6 GREEN: in `create_note()` — call `get_recent_notes_for_dedup()` + `check_note_dedup()` from invariants before insert; audit success/denied
- [ ] 3.7 RED: write failing test `test_reopen_audits` asserting audit row written on reopen success/denied
- [ ] 3.8 GREEN: in `reopen_ticket()` — audit success after channel created; audit denied on ValueError
- [ ] 3.9 RED: write failing test `test_close_audits` and `test_subticket_create_audits`
- [ ] 3.10 GREEN: in `close_ticket()` + `create_subticket()` — add audit rows for success/denied paths
- [ ] 3.11 RED: write failing test `test_claim_button_denies_non_mod` asserting ephemeral error for non-mod user
- [ ] 3.12 GREEN: in `bot/utils/checks.py` — extract `is_mod_check(interaction) -> bool` predicate (no decorator); refactor `is_mod()` to call it; in `bot/cogs/tickets.py` `claim_button` — gate with `if not await is_mod_check(interaction): send ephemeral error`
- [ ] 3.13 RED: write failing test `test_close_button_denies_non_author_non_mod` asserting ephemeral error
- [ ] 3.14 GREEN: in `close_button` — gate with `if user != author and not await is_mod_check(interaction): send ephemeral error`
- [ ] 3.15 RED: write failing test `test_reopen_by_ticket_number` asserting `/reopen ticket:#0003` resolves ticket #3 from any channel
- [ ] 3.16 GREEN: in `bot/cogs/tickets.py` `reopen()` — change signature to `ticket_ref: str | None = None`; call `parse_ticket_ref()` → `get_ticket_by_number()` or `get_ticket()` + guild check; preserve legacy channel lookup when no arg
- [ ] 3.17 REFACTOR: extract `_resolve_ticket_for_reopen(bot, ctx, ticket_ref)` helper to keep `reopen()` under 50 lines

## Phase 4: Dashboard Changes (PR 3)

- [ ] 4.1 RED: write failing vitest `ti001OpenToClaimed` asserting TS `validateStatusTransition("open", "claim")` returns success
- [ ] 4.2 GREEN: create `dashboard/lib/ticket-invariants.ts` — TS mirror of Python invariants (status transitions, permission matrix, parentId validation, dedup hash, note cap)
- [ ] 4.3 RED: write failing vitest `ti029DashboardReopenNoMutation` asserting `getReopenGuidance()` returns command string without DB update
- [ ] 4.4 GREEN: in `dashboard/lib/actions/ticket-actions.ts` — replace `reopenTicket()` with `getReopenGuidance(ticketId)` loading ticket+guild, checking `ticketCategoryId`, returning `{ ticketNumber, command }`; add `transferTicket` status='claimed' update; add note dedup+cap to `addTicketNote`; add author-only check to `deleteTicketNote`; add `getAuditRows(guildId, limit, offset)`; add `getTicketByNumber` query
- [ ] 4.5 RED: write failing vitest `ti030ReopenNoCategoryError` asserting missing ticketCategoryId returns error
- [ ] 4.6 GREEN: in `getReopenGuidance()` — check guild.ticketCategoryId; return error if missing
- [ ] 4.7 RED: write failing vitest for TI-031 (note cap), TI-032 (delete ownership), TI-034 (under cap), TI-035 (author delete own)
- [ ] 4.8 GREEN: enforce cap=50 + dedup in `addTicketNote`; enforce authorId match in `deleteTicketNote`
- [ ] 4.9 RED: write failing vitest `ti038AuditPaginated` asserting paginated audit rows returned
- [ ] 4.10 GREEN: create `ReopenTicketDialog` component in `dashboard/app/.../tickets/_components/ReopenTicketDialog.tsx` — shows ticket number (copyable) + `/reopen ticket:#XXXX` command; update `TicketRowActions.tsx` to call `getReopenGuidance` and show dialog instead of direct mutation
- [ ] 4.11 RED: write failing vitest for TI-019→TI-021 (audit every success, every denied, guild scope) — dashboard-side assertions
- [ ] 4.12 GREEN: add `TicketAudit` type to `dashboard/lib/types.ts` (id, guildId, ticketId, action, actorId, outcome, reason, createdAt); create audit panel component in `dashboard/app/.../tickets/_components/AuditPanel.tsx` with pagination
- [ ] 4.13 GREEN: update `NotesPanel.tsx` — disable add-note form at cap=50 with message; show delete button only for own notes (compare authorId to session user)
- [ ] 4.14 GREEN: enable all 38 vitest contract tests (remove `describe.skip`) — verify each ScenarioID passes against TS invariant logic + server actions
- [ ] 4.15 REFACTOR: extract shared mock factories for ticket/guild/note across dashboard contract tests
