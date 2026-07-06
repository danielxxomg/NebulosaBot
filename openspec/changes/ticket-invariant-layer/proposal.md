# Proposal: Ticket Invariant Layer (B5)

## Intent

Bot and dashboard enforce ticket invariants independently → 6 concrete drifts (reopen zombie, transfer status mismatch, ungated buttons, missing note cap/ownership, permission divergence). No shared specification exists. B5 establishes a single source-of-truth spec + mirrored contract tests so both sides enforce identical rules.

## Scope

### In Scope
1. **Permission**: Gate Claim button (`@is_mod()`) and Close button (author OR mod). Both currently ungated.
2. **Reopen**: Dashboard replaces DB-only reopen (zombie) with Discord deeplink. Bot keeps new-channel behavior.
3. **Transfer**: Unify to `claimedBy` + `status='claimed'` both sides. Migration normalizes existing rows.
4. **Notes**: Enforce cap 50 + author-only delete on dashboard. Add dedup (SHA256 hash + 2s window).
5. **Shared invariant spec**: `openspec/specs/ticket-invariants/spec.md` — status state machine, permission matrix, idempotency rules.
6. **Contract tests**: pytest (bot) + vitest (dashboard) asserting same scenarios: status transitions, permission matrix, 6 drifts.
7. **Sub-tickets**: Document flat depth-max-2 (already enforced, no code change).
8. **Audit table**: `ticket_audit` (ticketId, action, actorId, outcome, reason, timestamp). Persistent, queryable from dashboard.

### Out of Scope
- Close-to-archive redesign (close keeps deleting channel)
- Dashboard close/claim actions (stay bot-only)
- Mod-tier dashboard access (stays admin-only)
- RLS on ticket table (documented follow-up risk)
- Per-ticket channel permission scoping
- Live CDC end-to-end verification (deferred)

## Capabilities

### New Capabilities
- `ticket-invariants`: Shared specification for ticket lifecycle invariants — status state machine (open→claimed→closed→reopened, invalid transitions), permission matrix (admin/mod/author/user), idempotency rules (status-guards, note dedup hash), parentId FK constraints (depth-max-2). Single source-of-truth for bot + dashboard.

### Modified Capabilities
- `ticket-service`: Transfer MUST also set `status='claimed'`. Note dedup enforcement (SHA256 + 2s window). Audit logging on all ticket operations.
- `ticket-views`: Claim button gated by `@is_mod()`. Close button gated by author OR mod.
- `dashboard-ticket-view`: Reopen action changes to Discord deeplink (not DB-only). Transfer sets `claimedBy` + `status='claimed'`. Notes enforce cap 50 + author-only delete. Audit view added.

## Approach

- **Bot**: Extract invariants into `bot/services/ticket_invariants.py`. TicketService + button callbacks call it. Audit rows written via service.
- **Dashboard**: Mirror invariant checks in `ticket-actions.ts` (spec-mirrored, not code-shared). Reopen becomes deeplink.
- **Spec doc**: Single source-of-truth — both sides implement against it.
- **Contract tests**: pytest + vitest asserting same scenarios. Drift caught at build time.
- **Migration**: `005_ticket_audit.sql` (new table) + transfer-status normalization UPDATE (backup + review count first).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `bot/services/ticket_invariants.py` | New | Shared invariant checks + audit logging |
| `bot/services/ticket_service.py` | Modified | Transfer sets status, note dedup, audit calls |
| `bot/cogs/tickets.py` | Modified | Claim/Close button permission gates |
| `dashboard/lib/actions/ticket-actions.ts` | Modified | Reopen→deeplink, transfer status, notes cap/ownership |
| `dashboard/app/.../TicketRowActions.tsx` | Modified | Reopen button UX change |
| `dashboard/app/.../NotesPanel.tsx` | Modified | Cap enforcement, delete ownership |
| `openspec/specs/ticket-invariants/spec.md` | New | Shared invariant specification |
| `migrations/005_ticket_audit.sql` | New | Audit table + transfer normalization |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Scope >800 changed lines → chained PRs | High | delivery_strategy=auto-forecast, review budget=800 |
| Dashboard reopen deeplink broken if category deleted | Medium | Error UX: show message if guild has no ticketCategoryId |
| Transfer migration false-positives | Low | Backup + `SELECT COUNT(*)` review before running |
| `ticket_audit` table growth | Medium | Retention/TTL policy in design phase |
| Contract test mirroring discipline | Medium | CI runs both test suites; spec is source-of-truth |
| No RLS on ticket table | Low | Documented out-of-scope; audit queries guild-scoped |

## Rollback Plan

1. **Migration**: `ticket_audit` table is additive — drop table to rollback. Transfer normalization UPDATE: restore from backup if counts mismatch.
2. **Button gates**: Remove `@is_mod()` decorators from Claim/Close button callbacks to revert to ungated behavior.
3. **Dashboard reopen**: Revert `reopenTicket` action to DB-only status flip (restores zombie behavior but unblocks).
4. **Dashboard notes**: Remove cap/ownership checks from server actions.
5. **Spec doc + contract tests**: Delete `openspec/specs/ticket-invariants/` and test files.

## Dependencies

- None (self-contained change)

## Success Criteria

- [ ] All 6 drifts resolved: bot + dashboard enforce identical invariants
- [ ] Mirrored contract tests pass on both sides (pytest + vitest)
- [ ] `ticket_audit` table populated for all ticket operations
- [ ] Claim button rejects non-mods; Close button rejects non-author/non-mod
- [ ] Dashboard reopen opens Discord (not zombie DB flip)
- [ ] Dashboard transfer sets `status='claimed'` (not just `claimedBy`)
- [ ] Dashboard notes enforce cap 50 + author-only delete
- [ ] No regression in existing ~580 bot tests / ~152 dashboard tests
