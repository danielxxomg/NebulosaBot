# Design: runtime-hotfix

## Technical Approach

Ship one strict-TDD hotfix PR that keeps each production fix local: ticket audit failures become best-effort only after successful claim/close mutations, economy timestamp parsing moves to a tiny shared helper, Realtime close-hook wiring degrades without aborting startup tasks, and migrations are reconciled to the live `012_ticket_audit` state.

## Architecture Decisions

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Best-effort audit for successful claim/close | Audit gaps are possible, but user-facing Discord actions continue after DB mutation. | Use `try/except Exception` around only success-path `insert_audit_row` calls in `claim_ticket` and `close_ticket`; keep denied-path audit hard-fail because no mutation happened yet. |
| New `bot/utils/timeparse.py` vs adding to `bot/utils/time.py` | Existing `time.py` is a moderation duration parser; mixing DB timestamp parsing would blur responsibilities. | Create `timeparse.py` with `_to_datetime` and import it in `economy_service.py`. |
| Catch inside `_wire_close_logging` | Close-code logging may be skipped on SDK private API changes, but startup resilience improves. | Wrap the method body in `try/except AttributeError`, log WARNING, and return normally so health/poll/watchdog tasks still start. |
| Track live 012, remove stale 005 | Deleting 005 depends on git history for archaeology. | Keep `012_ticket_audit.sql` as the applied migration source of truth and delete stale `005_ticket_audit.sql`. |

## Data Flow

```text
Ticket claim/close
  invariant OK -> update ticket -> re-read -> cache/UI action continues
                                      └-> best-effort audit -> WARNING on failure

XP gain / daily
  DB member row -> _to_datetime(str|datetime|None) -> cooldown math -> DB update

Realtime start
  subscribe channel -> _wire_close_logging() [may warn]
                    -> health task + poll task + watchdog task
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `bot/services/ticket_service.py` | Modify | Add private best-effort audit helper or inline guarded calls for claim/close success audits only. |
| `bot/services/economy_service.py` | Modify | Import `_to_datetime`; use it for `lastXpGain`, `lastDaily`, and `lastDailyReset`; remove nested helper. |
| `bot/utils/timeparse.py` | Create | Pure timestamp parser for `datetime`, ISO strings, and `None`; invalid values return `None`. |
| `bot/core/realtime.py` | Modify | Guard `_wire_close_logging` against missing SDK private attributes with WARNING log. |
| `tests/test_ticket_service.py` | Modify | RED tests for claim/close success audit failure continuing after mutation and logging WARNING. |
| `tests/test_economy_service.py` | Modify | RED tests for string-type `lastXpGain` and shared helper behavior. |
| `tests/test_realtime.py` | Modify | RED test with client missing `_on_connect_error`, asserting startup tasks are created and WARNING logged. |
| `tests/test_migrations.py` | Modify | Assert `012_ticket_audit.sql` exists and stale `005_ticket_audit.sql` is absent. |
| `migrations/012_ticket_audit.sql` | Track | Commit the already-applied live migration. |
| `migrations/005_ticket_audit.sql` | Delete | Remove stale never-applied migration copy. |

## Interfaces / Contracts

```python
def _to_datetime(value: datetime | str | None) -> datetime | None:
    """Return a parsed datetime, or None for None/invalid DB timestamp values."""
```

`_wire_close_logging()` keeps its public contract: no return value and no startup-blocking exception for missing private SDK close-hook attributes.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Audit failure after successful claim/close mutation | Mock `insert_audit_row.side_effect`, assert service returns ticket, mutation occurred, WARNING logged. |
| Unit | Timestamp parsing in economy cooldowns | Use existing `frozen_clock`; set `lastXpGain` to ISO string and datetime variants. |
| Unit | Realtime startup resilience | Use a client double without `_on_connect_error`; assert `start()` creates all three background tasks. |
| Structural | Migration parity | Check 012 exists and 005 no longer exists. |
| Full suite | Regression coverage | Run `uv run pytest`. |

## Migration / Rollout

No live DB migration required: `012_ticket_audit.sql` is already applied on Supabase. Rollout is a single bot deploy plus repository migration parity cleanup.

## Open Questions

None.
