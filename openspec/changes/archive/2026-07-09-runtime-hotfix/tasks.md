# Tasks: runtime-hotfix

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 50–70 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | auto-forecast |
| Chain strategy | single-pr |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: single-pr
400-line budget risk: Low

## Phase 1: Shared Helper (timeparse.py)

- [x] 1.1 **RED**: Write tests in `tests/test_timeparse.py` for `_to_datetime` — scenarios: ISO string → datetime, datetime passthrough, None → None, invalid string → None
- [x] 1.2 **GREEN**: Create `bot/utils/timeparse.py` with `_to_datetime(value: datetime | str | None) -> datetime | None` — parse ISO strings, passthrough datetime, return None for None/invalid

## Phase 2: Ticket Audit Resilience

- [x] 2.1 **RED**: Add tests in `tests/test_ticket_service.py` — claim success audit failure: mock `insert_audit_row` to raise, assert claim UI action proceeds, WARNING logged
- [x] 2.2 **RED**: Add tests in `tests/test_ticket_service.py` — close success audit failure: mock `insert_audit_row` to raise, assert close UI action proceeds, WARNING logged
- [x] 2.3 **GREEN**: Modify `bot/services/ticket_service.py` — wrap success-path `insert_audit_row` calls in `claim_ticket`/`close_ticket` with `try/except Exception`, log WARNING, continue to UI action

## Phase 3: Economy Datetime Parsing

- [x] 3.1 **RED**: Add tests in `tests/test_economy_service.py` — string-type `lastXpGain` parsed without TypeError, cooldown comparison works
- [x] 3.2 **GREEN**: Modify `bot/services/economy_service.py` — import `_to_datetime` from `bot.utils.timeparse`, use for `lastXpGain`, `lastDaily`, `lastDailyReset`; remove nested helper

## Phase 4: Realtime Startup Resilience

- [x] 4.1 **RED**: Add test in `tests/test_realtime.py` — client missing `_on_connect_error`: assert `start()` creates health/poll/watchdog tasks, WARNING logged
- [x] 4.2 **GREEN**: Modify `bot/core/realtime.py` — wrap `_wire_close_logging` body in `try/except AttributeError`, log WARNING, return normally

## Phase 5: Migration Parity

- [x] 5.1 **RED**: Add assertions in `tests/test_migrations.py` — `012_ticket_audit.sql` exists, `005_ticket_audit.sql` absent
- [x] 5.2 **GREEN**: `git add migrations/012_ticket_audit.sql` and `git rm migrations/005_ticket_audit.sql`

## Phase 6: Final Verification

- [x] 6.1 Run `uv run pytest` — all tests green, no regressions
