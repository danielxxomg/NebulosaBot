# Tasks: Refactor Ticket Complexity

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 500–700 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Characterization tests + 4 pure helpers + protocol | PR 1 | Base: main; includes `tests/test_ticket_helpers.py` + `bot/utils/ticket_helpers.py` |
| 2 | Service wiring + `_build_reopen_channel` extraction | PR 2 | Base: main (after PR 1); includes `bot/services/ticket_service.py` + `tests/test_ticket_service.py` |
| 3 | Cog + view wiring + mock updates | PR 3 | Base: main (after PR 2); includes `bot/cogs/tickets.py`, `bot/views/tickets.py`, test mocks |

---

## Phase 1: Characterization Tests & Pure Helpers (PR 1)

- [x] 1.1 **RED** — Write characterization tests in `tests/test_ticket_helpers.py` for `build_ticket_overwrites()`: valid guild/author/mod_role, missing role, missing author, both None
- [x] 1.2 **RED** — Write characterization tests for `resolve_mod_role()`: valid role_id found, invalid ID returns None, missing role returns None
- [x] 1.3 **RED** — Write characterization tests for `resolve_member_safe()`: valid member found, invalid ID returns None, missing member returns None
- [x] 1.4 **RED** — Write characterization tests for `resolve_category_name()`: valid category found via DB, missing category returns fallback, DB error returns fallback
- [x] 1.5 **GREEN** — Add `TicketCategoryReader` Protocol to `bot/utils/ticket_helpers.py` exposing `get_ticket_category` only
- [x] 1.6 **GREEN** — Implement `build_ticket_overwrites()` in `bot/utils/ticket_helpers.py`
- [x] 1.7 **GREEN** — Implement `resolve_mod_role()` and `resolve_member_safe()` in `bot/utils/ticket_helpers.py`
- [x] 1.8 **GREEN** — Implement `async resolve_category_name()` in `bot/utils/ticket_helpers.py`
- [x] 1.9 **REFACTOR** — Verify all new helper tests pass; run `uv run pytest tests/test_ticket_helpers.py`

## Phase 2: Service Wiring & Reopen Extraction (PR 2)

- [x] 2.1 **RED** — Write characterization tests in `tests/test_ticket_service.py` for `create_ticket_channel` permission overwrites, member resolution, and mod role resolution paths
- [x] 2.2 **RED** — Write characterization tests for `reopen_ticket` channel-construction block: name, category, permission overwrites, Spanish invariant error text
- [x] 2.3 **GREEN** — Wire `create_ticket_channel` in `bot/services/ticket_service.py` to call `build_ticket_overwrites()`, `resolve_mod_role()`, `resolve_member_safe()` from `ticket_helpers`
- [x] 2.4 **GREEN** — Extract `_build_reopen_channel()` as private async method in `TicketService`; wire `reopen_ticket` to call it
- [x] 2.5 **GREEN** — Wire `resolve_category_name()` in `create_ticket_channel` for category name resolution
- [x] 2.6 **REFACTOR** — Verify service characterization tests pass; Spanish error text unchanged; run `uv run pytest tests/test_ticket_service.py`

## Phase 3: Cog & View Wiring (PR 3)

- [x] 3.1 **RED** — Write characterization tests in `tests/test_tickets_cog.py` for subticket role/category resolution paths
- [x] 3.2 **RED** — Write characterization tests in `tests/test_ticket_views.py` for modal mod-role resolution after config lookup
- [x] 3.3 **GREEN** — Wire `bot/cogs/tickets.py` subticket creation to use `resolve_mod_role()` and `resolve_category_name()` from `ticket_helpers`
- [x] 3.4 **GREEN** — Wire `bot/views/tickets.py` modal handler to use `resolve_mod_role()` from `ticket_helpers`
- [x] 3.5 **GREEN** — Update mock fixtures in `tests/test_tickets_cog.py` and `tests/test_ticket_views.py` for new helper call paths
- [x] 3.6 **REFACTOR** — Run full suite `uv run pytest`; verify 341+ tests pass, zero behavior changes, no import cycles

## Phase 4: Verification & Cleanup

- [ ] 4.1 Verify `reopen_ticket` LOC dropped from 137 to ~80
- [ ] 4.2 Verify service LOC dropped from 1,069 to ~950
- [ ] 4.3 Run `uv run pytest --cov=bot --cov-report=term`; verify coverage ≥ 0.70
- [ ] 4.4 Verify no duplication remains for extracted patterns across all call sites
