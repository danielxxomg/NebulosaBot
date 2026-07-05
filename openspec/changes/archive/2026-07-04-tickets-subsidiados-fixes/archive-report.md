# Archive Report: tickets-subsidiados-fixes

## Change Summary

Fixed 4 pre-push blockers in `bot/cogs/tickets.py` and `bot/services/ticket_service.py`:

| Blocker | Fix | Files |
|---------|-----|-------|
| B1 | `/note list` privacy — slash ephemeral, prefix DM to author + channel confirmation | `tickets.py` |
| B2 | `/reopen` status guard — service `ValueError` + cog error embed with actual status | `ticket_service.py`, `tickets.py` |
| B3 | `/subticket create` parent-owner access — overwrites + mention for parent author, not invoker | `tickets.py` |
| B4 | DB error handling — scoped try/except + `error_embed()` + `logging.exception()` on critical DB calls | `tickets.py` |

Out of scope: B5 (dashboard divergence → separate change `ticket-invariant-layer`).

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| `ticket-subsidiados` | Updated | 3 MODIFIED (Staff notes, Ticket reopen, Sub-ticket creation), 1 ADDED (Error handling in new commands) |
| `ticket-service` | Updated | 1 MODIFIED (reopen_ticket method — added status guard) |

### Source of Truth Updated

- `openspec/specs/ticket-subsidiados/spec.md`
- `openspec/specs/ticket-service/spec.md`

## Archive Contents

- `proposal.md` ✅
- `specs/ticket-subsidiados/spec.md` ✅
- `specs/ticket-service/spec.md` ✅
- `design.md` ✅
- `tasks.md` ✅ (24/24 tasks complete)
- `verify-report.md` ✅

## Verify Verdict

**PASS WITH WARNINGS** (orchestrator override)

The sdd-verify sub-agent reported FAIL due to a false CRITICAL: targeted pytest commands (`uv run pytest tests/test_tickets_cog.py -v` and `uv run pytest tests/test_ticket_service.py -v`) exited non-zero because the repository's global `--cov-fail-under=70` applied to file-scoped runs (26.13% and 8.75% respectively). All tests passed; the exit code was from coverage, not test failures.

The orchestrator overruled to PASS WITH WARNINGS because:
- All 546 tests pass, full suite at 78.42% coverage (above 70% gate)
- 23/23 spec scenarios compliant
- B5 boundary respected (no dashboard changes)
- No AGENTS.md violations
- The pytest config was fixed in commit `834a83d`: moved `--cov-fail-under` out of `addopts` to Makefile/CI targets

## Final Test State

| Metric | Value |
|--------|-------|
| Total tests | 546 passed |
| Coverage | 78.42% (gate: 70%) |
| Targeted tests | 70 cog + 36 service = 106 new/modified |
| Spec scenarios | 23/23 compliant |
| B5 boundary | Clean — no dashboard changes |

## Commits

| Hash | Message |
|------|---------|
| `ee29361` | `fix(tickets): note list privacy — ephemeral slash + DM prefix (B1)` |
| `eeb71f2` | `fix(tickets): reopen status guard — service ValueError + cog embed (B2)` |
| `f0368d8` | `fix(tickets): subticket parent-owner access grant (B3)` |
| `21908b2` | `fix(tickets): scoped DB error handling in new commands (B4)` |
| `6951396` | `chore(openspec): mark tickets-subsidiados-fixes tasks complete` |
| `6a7b134` | `fixup! ee29361 — B1 empty-state privacy` |
| `269d422` | `fixup! eeb71f2 — B2 ValueError catch with exact Spanish status` |
| `834a83d` | `fix(pytest): move --cov-fail-under out of addopts to Makefile/CI targets` |

## Warnings Carried Forward

1. **Fixup commits need autosquash**: `git rebase --autosquash 6e9ddc0` before push (mechanical).
2. **B2 design.md vs tasks.md divergence**: design.md showed a pre-service cog guard; tasks.md specified catch-from-service. tasks.md was authoritative. Implementation follows tasks.md.
3. **Mypy warning at `tickets.py:1301`**: `Member | None` assignment typing. Inherited debt, not introduced by this change.
4. **tickets.py coverage 74%**: Below preferred 80%, above gate 70%. Acceptable for a 1500+ line file.
5. **Service test B2 assertion uses substring regex**: Cog tests cover exact text. Non-blocking.

## Follow-ups

- **B5 dashboard divergence** → deferred to separate change `ticket-invariant-layer`
- **pytest config SUGGESTION** → resolved in commit `834a83d`

## Engram Traceability

| Artifact | Observation ID | Topic Key |
|----------|---------------|-----------|
| Apply progress | #637 | `sdd/tickets-subsidiados-fixes/apply-progress` |
| Verify report | #646 | `sdd/tickets-subsidiados-fixes/verify-report` |
| Archive report | (this save) | `sdd/tickets-subsidiados-fixes/archive-report` |
