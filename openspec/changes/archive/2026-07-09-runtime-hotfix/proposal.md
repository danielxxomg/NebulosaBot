# Proposal: runtime-hotfix

## Intent

Three production bugs cause degraded runtime: ticket claim/close mutations succeed but audit failure aborts the UI action, XP cooldown crashes on unparsed datetime strings, and Realtime `_wire_close_logging` AttributeError prevents health/poll/watchdog tasks from starting. Migration repo also lacks parity with applied state.

## Scope

### In Scope
- Ticket audit resilience: wrap `insert_audit_row` in try/except + WARNING after claim/close mutations
- Datetime parsing: extract `_to_datetime` to shared helper (`bot/utils/timeparse.py`), use in `gain_xp` + `claim_daily`
- Realtime resilience: wrap `_wire_close_logging` body in try/except AttributeError so health/poll/watchdog still start
- Migration parity: track `012_ticket_audit.sql`, delete stale `005_ticket_audit.sql`

### Out of Scope
- `Member.from_db_row` full timestamp parse refactor (follow-up)
- Product UX (modals, pin, avatar, manual docs)
- New features

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ticket-service`: Audit logging on claim/close becomes best-effort — failure MUST NOT abort the UI action (channel delete on close, role assignment on claim). Audit gaps logged at WARNING.
- `economy-service`: XP gain cooldown check MUST parse `lastXpGain` from ISO string to datetime before comparison. Shared helper used by both `gain_xp` and `claim_daily`.
- `cache-sync-realtime`: `_wire_close_logging` MUST handle missing `_on_connect_error` SDK attribute gracefully (try/except + WARNING) so health/poll/watchdog tasks still start.

## Approach

Single focused hotfix PR, ~50-70 lines. Each fix is independent:

1. **Ticket audit**: `try/except Exception` around each `insert_audit_row` call in `claim_ticket`/`close_ticket`, log at WARNING, continue to UI action.
2. **Datetime**: Extract `_to_datetime` from `claim_daily` to `bot/utils/timeparse.py`, import in both `gain_xp` and `claim_daily`.
3. **Realtime**: Wrap `_wire_close_logging` method body in `try/except AttributeError`, log WARNING, return normally.
4. **Migration**: `git add migrations/012_ticket_audit.sql`, `git rm migrations/005_ticket_audit.sql`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `bot/services/ticket_service.py` | Modified | try/except around audit inserts in claim/close |
| `bot/services/economy_service.py` | Modified | Use shared `_to_datetime` in `gain_xp` cooldown |
| `bot/utils/timeparse.py` | New | Shared ISO datetime string parser |
| `bot/core/realtime.py` | Modified | try/except in `_wire_close_logging` |
| `migrations/012_ticket_audit.sql` | New (tracked) | Git-track existing file |
| `migrations/005_ticket_audit.sql` | Removed | Stale, never applied, content in 012 |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Silent audit gaps | Med | WARNING-level logs + existing monitoring |
| `timeparse.py` import path changes | Low | Pure function, no side effects, straightforward |
| SDK attr renamed not removed | Low | getattr/try/except handles both cases |

## Rollback Plan

Revert the single commit. Each fix is independent — can also revert individual files:
- Ticket audit: remove try/except wrappers, restore direct calls
- Datetime: inline `_to_datetime` back into `claim_daily`, remove `timeparse.py`
- Realtime: remove try/except wrapper
- Migration: `git rm migrations/012_ticket_audit.sql`, restore `005_ticket_audit.sql` from git history

## Dependencies

- `migrations/012_ticket_audit.sql` already applied live on Supabase vozkcckiybebhcclrasa

## Success Criteria

- [ ] Ticket claim/close succeeds even when audit insert fails (WARNING logged)
- [ ] `gain_xp` handles string-type `lastXpGain` without TypeError
- [ ] Realtime health/poll/watchdog tasks start even when `_on_connect_error` is missing
- [ ] `migrations/012_ticket_audit.sql` tracked in git, `005_ticket_audit.sql` removed
- [ ] All existing tests pass + new tests for each fix
