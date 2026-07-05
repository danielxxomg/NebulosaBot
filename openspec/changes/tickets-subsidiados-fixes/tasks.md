# Tasks: tickets-subsidiados-fixes

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 250–400 (production ~120, tests ~200) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR — 4 independent work-unit commits |
| Delivery strategy | auto-forecast |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: stacked-to-main
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | B1 — note list privacy | PR 1 (single) | Slash ephemeral + prefix DM routing |
| 2 | B2 — reopen status guard | PR 1 (single) | Service ValueError + cog error embed |
| 3 | B3 — subticket parent-owner access | PR 1 (single) | Parent author overwrites + mention |
| 4 | B4 — DB error handling | PR 1 (single) | Scoped try/except + error_embed |

## Phase 1: B1 — `/note list` Privacy

- [x] 1.1 **RED** `tests/test_tickets_cog.py`: test slash `/note list` calls `ctx.send(embed=..., ephemeral=True)` when `ctx.interaction` is not None
- [x] 1.2 **RED** `tests/test_tickets_cog.py`: test prefix `/note list` calls `ctx.author.send(embed=...)` with notes and `ctx.send` with confirmation-only embed (no note content)
- [x] 1.3 **GREEN** `bot/cogs/tickets.py:~1497-1531`: route by `ctx.interaction` — slash → ephemeral; prefix → DM to author + channel confirmation
- [x] 1.4 **GREEN** `bot/cogs/tickets.py`: catch `discord.Forbidden`/`discord.HTTPException` on DM failure, log, send error embed without note content
- [x] 1.5 **VERIFY** `uv run pytest tests/test_tickets_cog.py -k note -v` — all B1 tests pass

## Phase 2: B2 — `/reopen` Status Guard

- [x] 2.1 **RED** `tests/test_ticket_service.py`: test `reopen_ticket` raises `ValueError` when status is `open`
- [x] 2.2 **RED** `tests/test_ticket_service.py`: test `reopen_ticket` raises `ValueError` when status is `claimed`
- [x] 2.3 **RED** `tests/test_tickets_cog.py`: test `/reopen` on non-closed sends error embed with exact Spanish text: "Solo se pueden reabrir tickets cerrados. Estado actual: {status}"
- [x] 2.4 **GREEN** `bot/services/ticket_service.py:~348-437`: add status guard after `get_ticket` — raise `ValueError` if `status != "closed"`
- [x] 2.5 **GREEN** `bot/cogs/tickets.py:~1333-1380`: catch `ValueError` from service, send error embed with actual status
- [x] 2.6 **VERIFY** `uv run pytest tests/test_ticket_service.py tests/test_tickets_cog.py -k reopen -v` — all B2 tests pass

## Phase 3: B3 — Sub-ticket Parent-Owner Access

- [x] 3.1 **RED** `tests/test_tickets_cog.py`: test `/subticket create` overwrites include parent owner (not invoker) with `read_messages=True, send_messages=True`
- [x] 3.2 **RED** `tests/test_tickets_cog.py`: test channel `send` mentions parent owner, not invoker
- [x] 3.3 **RED** `tests/test_tickets_cog.py`: test invoker IS parent owner — access already granted, no duplicate overwrite
- [x] 3.4 **GREEN** `bot/cogs/tickets.py:~1154-1329`: resolve `parent_author_id` from `parent_row["authorId"]`, build overwrite for parent author, remove invoker overwrite, mention parent_author
- [x] 3.5 **VERIFY** `uv run pytest tests/test_tickets_cog.py -k subticket -v` — all B3 tests pass

## Phase 4: B4 — DB Error Handling

- [ ] 4.1 **RED** `tests/test_tickets_cog.py`: test `get_notes` raises → `error_embed` returned, `logger.exception` called, no raw traceback
- [ ] 4.2 **RED** `tests/test_tickets_cog.py`: test critical DB call in `/subticket create` raises → `error_embed` + `logger.exception`
- [ ] 4.3 **RED** `tests/test_tickets_cog.py`: test critical DB call in `/reopen` raises → `error_embed` + `logger.exception`
- [ ] 4.4 **GREEN** `bot/cogs/tickets.py`: wrap `get_notes`, `get_ticket_by_channel`, `create_subticket`, `reopen_ticket`, `transfer_ticket`, `create_note`, `delete_note` calls in tight `try/except Exception` → `logger.exception` + `error_embed` + `return`
- [ ] 4.5 **VERIFY** `uv run pytest tests/test_tickets_cog.py -v` — all B4 tests pass

## Phase 5: Final Verification

- [ ] 5.1 `uv run pytest --cov=bot --cov-report=term-missing` — all tests pass, coverage ≥ 0.70
- [ ] 5.2 Manual review: no raw tracebacks possible on DB failure paths
- [ ] 5.3 Git: 4 work-unit commits (B1→B2→B3→B4), each independently revertable

## Dependencies

- B1–B4 are independent — no cross-blocker dependencies
- Within each blocker: RED tests MUST complete before GREEN implementation
- Phase 5 depends on all blockers complete
