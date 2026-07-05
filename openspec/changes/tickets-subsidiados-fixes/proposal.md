# Proposal: tickets-subsidiados-fixes

## Intent

4 validated pre-push blockers in `bot/cogs/tickets.py` and `bot/services/ticket_service.py` block the 12-commit push to origin: data-exposure in `/note list`, duplicate-channel via `/reopen`, over-grant in `/subticket create`, raw tracebacks on DB failure.

## Scope

### In Scope

- **B1** `/note list` prefix handling — DM notes to the mod in prefix commands; ephemeral in slash
- **B2** `/reopen` status guard — error embed when target is not closed (state actual status)
- **B3** `/subticket create` access — grant channel access to parent ticket author, not invoker
- **B4** Error handling — wrap critical DB calls (`get_notes`, other DB calls in 4 new commands) in try/except

### Out of Scope

- **B5** Dashboard divergence — deferred to `ticket-invariant-layer`
- Tech debt #545, tunnel/webhook pivot (`cache-sync-realtime`)

## Capabilities

### Modified Capabilities

- `ticket-subsidiados`: B1 (note list privacy), B2 (reopen guard), B3 (subticket access grant), B4 (error handling in commands)
- `ticket-service`: B2 (reopen_ticket status guard at service layer)

### New Capabilities

None — all changes patch existing specs.

## Approach

| Blocker | Fix Direction | Files |
|---------|--------------|-------|
| B1 | Slash: ephemeral. Prefix: DM embed to `ctx.author`. | `tickets.py:1497-1531` |
| B2 | Status guard in `reopen_ticket` (raise `ValueError`). Cog sends error embed with actual status. | `ticket_service.py:348-437`, `tickets.py:1333-1380` |
| B3 | Grant channel overwrites to parent_owner, mention parent_owner not invoker. | `tickets.py:1154-1329` |
| B4 | Try/except on `get_notes` + critical DB calls. `logging.exception()` + `error_embed()`. | `tickets.py:1146,1453,1514` |

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `bot/cogs/tickets.py` | Modified | B1-B4 patches |
| `bot/services/ticket_service.py` | Modified | B2 status guard |
| `openspec/specs/ticket-subsidiados/spec.md` | Modified | Delta spec for B1-B4 |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| B3 channel overwrite race (parent_owner offline) | Low | Discord.py handles offline member overwrites; verify in test |
| B4 catching too broadly hides real bugs | Low | Scope try/except to individual DB calls, log full traceback |
| B5 deferred — dashboard still bypasses bot invariants | Medium | Explicitly out-of-scope; track as follow-up change |
| B2 service-level guard may break future callers | Low | Raise `ValueError` (consistent with other service errors) |

## Rollback Plan

Each blocker is an isolated patch. Revert individual commits per blocker. No schema changes, no migrations.

## Dependencies

- None.

## Success Criteria

- [ ] `/note list` prefix → DM to mod, never channel
- [ ] `/reopen` non-closed → error embed with actual status
- [ ] `/subticket create` → parent_owner gets access
- [ ] No raw tracebacks on DB failure
- [ ] `uv run pytest` passes
