# Tasks: Ticket Category Operations

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 650–800 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (foundation) → PR 2 (service) → PR 3 (views + i18n) |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Pure invariants + DB count query + tests | PR 1 | base: main; foundation layer, no service wiring |
| 2 | Service guard + edit_ticket_category + tests | PR 2 | base: main (after PR 1 merges); depends on PR 1 invariants |
| 3 | View button/select + i18n + view tests | PR 3 | base: main (after PR 2 merges); full integration |

## Phase 1: Foundation — Pure Invariants + DB Query

- [x] 1.1 RED: Write failing tests for `check_one_ticket_per_user_per_category` in `tests/test_ticket_invariants.py` — all 6 spec scenarios (open blocked, claimed blocked, no open allowed, subticket skips, null category skips, closed frees slot)
- [x] 1.2 GREEN: Add `check_one_ticket_per_user_per_category(user_id, category_id, parent_id, count_fn)` to `bot/services/ticket_invariants.py` — pure function, raises `ValueError` on violation
- [x] 1.3 RED: Write failing tests for `check_can_edit_category` in `tests/test_ticket_invariants.py` — mod allowed, non-mod denied
- [x] 1.4 GREEN: Add `check_can_edit_category(actor_id, ticket, *, is_mod)` to `bot/services/ticket_invariants.py` — mirrors `check_can_unclaim` signature pattern
- [x] 1.5 RED: Write failing tests for `count_user_open_tickets_in_category` in `tests/test_ticket_db.py` — 4 filters (guild_id, author_id, category_id, open|claimed statuses) + `exclude_ticket_id` kwarg
- [x] 1.6 GREEN: Add `count_user_open_tickets_in_category(guild_id, author_id, category_id, *, exclude_ticket_id=None)` to `bot/core/db/ticket_db.py`
- [x] 1.7 REFACTOR: Run `uv run pytest tests/test_ticket_invariants.py tests/test_ticket_db.py` — all pass

## Phase 2: Service — create_ticket Guard + edit_ticket_category

- [x] 2.1 RED: Write failing tests in `tests/test_ticket_service.py` for `create_ticket` guard — second ticket in same category blocked, different category allowed, closed frees slot, subticket bypasses, null categoryId bypasses
- [x] 2.2 GREEN: Add per-user-per-category guard in `TicketService.create_ticket()` before the numbering loop — call `count_user_open_tickets_in_category` + `check_one_ticket_per_user_per_category`; skip when `parent_id` or `category_id is None`; raise `ValueError` on violation; caller (`create_ticket_channel`) deletes orphan channel on `ValueError`
- [x] 2.3 RED: Write failing tests in `tests/test_ticket_service.py` for `edit_ticket_category` — all spec scenarios (DB+rename, rename failure warning, audit row, mod enforcement, closed rejected, limit violation, empty category, exclude_ticket_id, same-category no-op)
- [x] 2.4 GREEN: Add `edit_ticket_category(ticket_id, new_category_id, *, channel, actor_id, is_mod=False)` to `TicketService` — fetch ticket, check closed, check_can_edit_category, count + limit check with exclude_ticket_id, DB update, audit, channel rename (catch `HTTPException`), return `tuple[Ticket, bool]`
- [x] 2.5 REFACTOR: Run `uv run pytest tests/test_ticket_service.py` — all pass

## Phase 3: Views + i18n — Edit Button + Ephemeral Select

- [x] 3.1 Add i18n keys to `bot/locales/en.json`: `tickets.actions.edit_category`, `tickets.actions.edit_category_button`, `tickets.actions.edit_category_success`, `tickets.actions.edit_category_rename_warning`, `tickets.actions.edit_category_limit_title`, `tickets.actions.edit_category_limit_description`, `tickets.actions.edit_category_closed_description`, `tickets.actions.edit_category_mods_only_title`, `tickets.actions.edit_category_mods_only_description`, `tickets.actions.edit_category_no_categories`
- [x] 3.2 Add corresponding keys to `bot/locales/es.json` with Spanish translations
- [x] 3.3 RED: Write failing tests in `tests/test_ticket_views.py` — button label i18n, mod gate, ephemeral select shown, closed reject, limit violation specific UX, rename failure warning, no categories message
- [x] 3.4 GREEN: Add persistent "Edit Category" button (`custom_id="ticket:edit-category"`) to `TicketActionsView` in `bot/views/tickets.py` — `@is_mod()` gate, fetch active categories, show ephemeral `_EditCategorySelect` (timeout=300s)
- [x] 3.5 GREEN: Add `_EditCategorySelect` callback — re-run `is_mod_check()` on submit, reject closed tickets, call `edit_ticket_category()`, handle `ValueError` with specific limit UX, handle rename warning, confirm success
- [x] 3.6 Update `TicketActionsView.__init__` to resolve edit button label via `t()` at interaction time
- [x] 3.7 REFACTOR: Run `uv run pytest tests/test_ticket_views.py` — all pass

## Phase 4: Final Verification

- [x] 4.1 Run `uv run pytest` — full suite green, no regressions
- [x] 4.2 Verify `python -m py_compile bot/__main__.py` — no syntax errors
