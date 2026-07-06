# Design: Ticket Invariant Layer

## Technical Approach

Keep Discord side effects in the bot and enforce the same invariant contract in Python services, Discord button callbacks, and dashboard server actions. The authoritative implementation inputs are the four delta specs plus the contract scenario table below; pytest and Vitest MUST mirror every `ScenarioID` one-for-one. Dashboard reopen becomes guidance only, never a DB mutation.

## Architecture Decisions

| Decision | Choice | Tradeoff | Rationale |
|---|---|---|---|
| Invariant layer | `bot/services/ticket_invariants.py` + TS mirror in `dashboard/lib/actions/ticket-actions.ts` | No runtime code sharing | Fits current bot/dashboard split and keeps services testable. |
| Contract source | This design table → mirrored `SCENARIOS` in `tests/contract/test_ticket_invariants.py` and `dashboard/__tests__/contract/ticket-invariants.test.ts` | Manual mirroring | Explicit IDs make drift reviewable and CI-catchable. |
| Reopen | Bot `/reopen` accepts `ticket_ref`; dashboard shows command guidance | Dashboard cannot create channels | Closed ticket channels are deleted; DB-only reopen creates zombies. |
| Dashboard category gate | Modal MUST require configured `guild.ticketCategoryId`; missing config shows error and no modal | Dashboard cannot verify deleted Discord category | Prevents telling admins to run a command known to fail. |
| Note dedup | App-level SHA256 normalized-content compare, no `contentHash` column | Small per-author query | Avoids schema migration risk; 2s window is tiny and indexed. |
| Audit | Add `ticket_audit`, RLS enabled, no anon policies, service-role queries with `.eq("guildId", ...)` | No FK | Project already relies on app-level FK validation. |

## Data Flow

```text
Discord button/command -> inline permission -> invariant -> DB -> ticket_audit
Dashboard action       -> admin auth         -> invariant -> DB -> ticket_audit
Dashboard Reopen       -> load guild+ticket  -> if no ticketCategoryId: error
                       -> else show `/reopen ticket:#0003`
Bot `/reopen ticket:#0003` -> resolve by guild+number -> create channel -> update ticket
```

## Button Permission Pattern

`@is_mod()` is an app-command decorator and MUST NOT decorate `discord.ui.button` callbacks. Extract a shared predicate in `bot/utils/checks.py` and make `is_mod()` wrap it.

```python
async def is_mod_check(interaction: discord.Interaction) -> bool: ...

async def claim_button(self, interaction, button):
    if not await is_mod_check(interaction):
        await interaction.response.send_message(embed=error_embed("Denied", "Mods only"), ephemeral=True)
        return

async def close_button(self, interaction, button):
    ticket_row, error = await self._get_ticket(bot, channel_id)
    if interaction.user.id != int(ticket_row["authorId"]) and not await is_mod_check(interaction):
        await interaction.response.send_message(embed=error_embed("Denied", "Author or mod only"), ephemeral=True)
        return
```

## `/reopen` Ticket Reference Design

`bot/cogs/tickets.py` keeps `@commands.hybrid_command(name="reopen") @is_mod()` and changes signature to `ticket_ref: str | None = None`. Parse the value (parser strips an optional `ticket:` prefix, then accepts `#0003`, `0003`, or a UUID) via new `Database.get_ticket_by_number(guild_id, ticket_number)` using `.eq("guildId", guild_id).eq("ticketNumber", ticket_number)`. UUID refs use `get_ticket(ticket_id)` plus guild check. The guidance text `/reopen ticket:#0003` is literally valid: the slash option is `ticket_ref` whose value `ticket:#0003` the parser strips to `#0003` → `ticket_number=3`. No arg preserves legacy `get_ticket_by_channel(str(ctx.channel.id))` for the 5s close/delete window. Bad, missing, wrong-guild, or non-closed tickets return `error_embed`; service still owns the status guard.

## Dashboard Reopen Guidance

Replace `reopenTicket()` mutation with `getReopenGuidance(ticketId)` and `ReopenTicketDialog`. The action MUST auth as guild admin, load ticket+guild, reject missing `ticketCategoryId` with “Ticket category is not configured”, and only then return `ticketNumber` plus `/reopen ticket:#0003`. It MUST NOT update `ticket`.

## File Changes

| File | Action | Description |
|---|---|---|
| `bot/utils/checks.py` | Modify | Add `is_mod_check()` predicate reused by decorator/buttons. |
| `bot/services/ticket_invariants.py` | Create | Status, permission, parentId, dedup hash helpers, audit reasons. |
| `bot/services/ticket_service.py` | Modify | Guards/audit; transfer same-user reject; note dedup; audit all operations. |
| `bot/core/database.py` | Modify | `get_ticket_by_number`, audit CRUD, recent notes query. |
| `bot/cogs/tickets.py` | Modify | Inline button gates; `/reopen(ticket_ref: str | None)`. |
| `dashboard/lib/actions/ticket-actions.ts` | Modify | TS mirror, guidance action, transfer status, note cap/dedup/ownership, audit queries. |
| `dashboard/app/(authenticated)/guilds/[guildId]/tickets/_components/*` | Modify/Create | Reopen dialog, notes cap UX, audit panel. |
| `dashboard/lib/types.ts` | Modify | Add `TicketAudit`. |
| `migrations/005_ticket_audit.sql` | Create | Audit table/indexes/RLS, note index, transfer normalization, pg_cron retention. |
| `tests/contract/test_ticket_invariants.py` | Create | One pytest per ScenarioID. |
| `dashboard/__tests__/contract/ticket-invariants.test.ts` | Create | One Vitest per ScenarioID. |

## Interfaces / Contracts

Note dedup has NO schema column. Normalize with `sha256(" ".join(content.strip().lower().split()))`; query recent notes by same ticket+author in the last 2 seconds and compare hashes in app code.

```sql
CREATE TABLE IF NOT EXISTS ticket_audit (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "guildId" TEXT NOT NULL, "ticketId" UUID NOT NULL, action TEXT NOT NULL, "actorId" TEXT, outcome TEXT NOT NULL CHECK (outcome IN ('success','denied','error')), reason TEXT, "createdAt" TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS idx_ticket_audit_ticket_history ON ticket_audit ("guildId","ticketId","createdAt" DESC);
CREATE INDEX IF NOT EXISTS idx_ticket_audit_guild_created ON ticket_audit ("guildId","createdAt" DESC);
CREATE INDEX IF NOT EXISTS idx_ticket_audit_guild_action ON ticket_audit ("guildId",action);
CREATE INDEX IF NOT EXISTS idx_ticket_note_ticket_author_created ON ticket_note ("ticketId","authorId","createdAt" DESC);
ALTER TABLE ticket_audit ENABLE ROW LEVEL SECURITY;
```

## Contract Scenarios

Both suites MUST mirror every row and include the `ScenarioID` in the test name. Dashboard tests for bot-only operations assert the pure TS invariant or that no dashboard mutation path exists.

| ScenarioID | Description | Given | When | Then | Bot-test | Dashboard-test |
|---|---|---|---|---|---|---|
| TI-001 | open→claimed | open | claim | status claimed, claimedBy set, audit success | `test_ti001_open_to_claimed` | `ti001OpenToClaimed` |
| TI-002 | open→closed | open | close | status closed, audit success | `test_ti002_open_to_closed` | `ti002OpenToClosedInvariant` |
| TI-003 | claimed→closed | claimed | close | status closed, audit success | `test_ti003_claimed_to_closed` | `ti003ClaimedToClosedInvariant` |
| TI-004 | closed→open | closed | reopen | new channel, status open | `test_ti004_closed_to_open` | `ti004ReopenGuidanceOnly` |
| TI-005 | invalid claim | closed | claim | denied + audit | `test_ti005_closed_claim_denied` | `ti005ClosedClaimDenied` |
| TI-006 | invalid reopen | open/claimed | reopen | denied, no channel | `test_ti006_non_closed_reopen_denied` | `ti006NonClosedNoGuidance` |
| TI-007 | claim no-overwrite | claimed by A | B or A claims | denied, A preserved | `test_ti007_claim_no_overwrite` | `ti007ClaimNoOverwrite` |
| TI-008 | transfer open | open, null claim | transfer B | claimedBy=B,status=claimed | `test_ti008_transfer_open_claims` | `ti008TransferOpenClaims` |
| TI-009 | transfer claimed | claimed A | transfer B | claimedBy=B,status=claimed | `test_ti009_transfer_reassigns` | `ti009TransferReassigns` |
| TI-010 | transfer same user | claimed A | transfer A | denied + audit | `test_ti010_transfer_same_user_denied` | `ti010TransferSameUserDenied` |
| TI-011 | valid subticket | parent exists same guild no parentId | create child | success | `test_ti011_subticket_valid` | `ti011SubticketValid` |
| TI-012 | parent missing | no parent row | create child | denied | `test_ti012_parent_missing_denied` | `ti012ParentMissingDenied` |
| TI-013 | self parent | parentId==id | create child | denied | `test_ti013_self_parent_denied` | `ti013SelfParentDenied` |
| TI-014 | depth max 2 | parent already child | create child | denied | `test_ti014_depth_denied` | `ti014DepthDenied` |
| TI-015 | same guild | parent guild A | child guild B | denied | `test_ti015_cross_guild_parent_denied` | `ti015CrossGuildParentDenied` |
| TI-016 | note dedup exact hash | same author note 1s ago | normalized duplicate | ValueError/denied | `test_ti016_note_dedup_denied` | `ti016NoteDedupDenied` |
| TI-017 | note outside window | same author note 5s ago | same content | allowed | `test_ti017_note_outside_window_allowed` | `ti017NoteOutsideWindowAllowed` |
| TI-018 | note different author | author A note 1s ago | author B same content | allowed | `test_ti018_note_different_author_allowed` | `ti018NoteDifferentAuthorAllowed` |
| TI-019 | audit all ops | claim/close/reopen/transfer/subticket/note add/list/delete | succeeds | one success row each | `test_ti019_audit_every_success` | `ti019AuditEverySuccess` |
| TI-020 | audit violations | permission/invariant fail | denied | denied row with reason | `test_ti020_audit_every_denied` | `ti020AuditEveryDenied` |
| TI-021 | audit scope | rows guild A+B | query A | only A rows | `test_ti021_audit_guild_scope` | `ti021AuditGuildScope` |
| TI-022 | create permission | user/admin/mod/author | create ticket | all allowed | `test_ti022_create_any_user` | `ti022CreateAnyUser` |
| TI-023 | claim permission | admin/mod/author/user | claim | admin+mod allowed; author/user denied | `test_ti023_claim_permission_matrix` | `ti023ClaimPermissionMatrix` |
| TI-024 | close permission | admin/mod/author/user | close | admin/mod/author allowed; user denied | `test_ti024_close_permission_matrix` | `ti024ClosePermissionMatrix` |
| TI-025 | reopen permission | admin/mod/author/user | reopen | admin+mod allowed; author/user denied | `test_ti025_reopen_permission_matrix` | `ti025ReopenPermissionMatrix` |
| TI-026 | transfer permission | admin/mod/author/user | transfer | bot: admin OR configured mod (`@is_mod()`); dashboard: admin only (documented divergence, decision #1 / engram #669) | `test_ti026_transfer_permission_matrix` | `ti026TransferPermissionMatrix` |
| TI-027 | notes/subticket permission | admin/mod/author/user | note CRUD/subticket | admin+mod allowed; others denied | `test_ti027_staff_ops_permission_matrix` | `ti027DashboardAdminOnlyStaffOps` |
| TI-028 | audit view permission | admin/mod/author/user | view audit | admin only | `test_ti028_audit_view_admin_only` | `ti028AuditViewAdminOnly` |
| TI-029 | drift: dashboard reopen | closed ticket | dashboard reopen | no ticket update; command shown | `test_ti029_reopen_by_number` | `ti029DashboardReopenNoMutation` |
| TI-030 | drift: category gate | no ticketCategoryId | dashboard reopen | error, no modal | `test_ti030_reopen_no_category_error` | `ti030ReopenNoCategoryError` |
| TI-031 | drift: note cap | 50 notes | add note | denied + disabled UI | `test_ti031_note_cap` | `ti031NoteCap` |
| TI-032 | drift: note delete ownership | note by A | B deletes | denied | `test_ti032_note_delete_owner_only` | `ti032NoteDeleteOwnerOnly` |
| TI-033 | drift: guild scope | ticket/note/audit guild B | guild A action/query | denied/no leak | `test_ti033_guild_scope` | `ti033GuildScope` |
| TI-034 | note added under cap | ticket #5 has 30 notes | author adds note | persisted, audit success | `test_ti034_note_under_cap` | `ti034NoteUnderCap` |
| TI-035 | author deletes own note | note by userA | userA deletes | deleted, audit success | `test_ti035_author_delete_own` | `ti035AuthorDeleteOwn` |
| TI-036 | action view render | newly created ticket channel | ticket opened | embed + claim/close buttons sent | `test_ti036_action_view_render` | `ti036ActionViewRender` |
| TI-037 | /reopen no-arg legacy | just-closed ticket, channel still exists (5s window) | mod runs `/reopen` (no arg) in channel | resolves by channel, new channel created | `test_ti037_reopen_noarg_legacy` | `ti037ReopenNoargLegacyInvariant` |
| TI-038 | audit paginated display | guild A has 200 audit rows | admin visits audit tab | paginated rows shown, newest first | `test_ti038_audit_paginated` | `ti038AuditPaginated` |

## Testing Strategy

Strict TDD: write failing pytest/Vitest first for each ScenarioID, then implement. Required gates: `uv run pytest` with coverage ≥0.70 and dashboard Vitest for changed dashboard tests.

## Migration / Rollout

Create `migrations/005_ticket_audit.sql` (004 exists). Add idempotent backup and normalization:

```sql
CREATE TABLE IF NOT EXISTS ticket_backup_claimed_open_20260706 AS SELECT * FROM ticket WHERE "claimedBy" IS NOT NULL AND status='open';
UPDATE ticket SET status='claimed' WHERE "claimedBy" IS NOT NULL AND status='open';
```

Retention uses Supabase `pg_cron`; enable the extension on the project, then schedule exactly:

```sql
SELECT cron.schedule('ticket_audit_retention','0 3 * * 0',$$DELETE FROM ticket_audit WHERE "createdAt" < now() - interval '90 days'$$);
```

## Open Questions

None.
