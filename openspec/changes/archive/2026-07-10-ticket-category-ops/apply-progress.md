# Apply Progress: ticket-category-ops

## Phase 1: Foundation — Pure Invariants + DB Query

### Status: COMPLETE (7/7 tasks)

### TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.1 | `tests/test_ticket_invariants.py` | Unit | ✅ 60/60 | ✅ Written (7 tests) | — (GREEN in 1.2) | ✅ 7 spec scenarios | ✅ E731 fixed |
| 1.2 | `tests/test_ticket_invariants.py` | Unit | N/A (new) | — (RED in 1.1) | ✅ 7/7 passed | ✅ Includes count_fn call verification | ✅ Clean |
| 1.3 | `tests/test_ticket_invariants.py` | Unit | ✅ 60/60 | ✅ Written (4 tests) | — (GREEN in 1.4) | ✅ 4 scenarios | ✅ Clean |
| 1.4 | `tests/test_ticket_invariants.py` | Unit | N/A (new) | — (RED in 1.3) | ✅ 4/4 passed | ✅ mod, non-mod-author, non-mod-other, mod-other | ✅ Clean |
| 1.5 | `tests/test_ticket_db.py` | Unit | ✅ 60/60 | ✅ Written (9 tests) | — (GREEN in 1.6) | ✅ 4 filters + exclude + no-exclude + raises | ✅ Added neq to FakeQueryBuilder |
| 1.6 | `tests/test_ticket_db.py` | Unit | N/A (new) | — (RED in 1.5) | ✅ 9/9 passed | ✅ Guild, author, category, status, exclude_ticket_id | ✅ Clean |
| 1.7 | `tests/test_ticket_invariants.py` + `tests/test_ticket_db.py` | Unit | — | — | — | — | ✅ 80/80 pass, ruff clean |

### Test Summary (Phase 1)

- **Total tests written**: 20 (7 invariant limit + 4 edit auth + 9 DB count)
- **Total tests passing**: 80/80 (60 baseline + 20 new)
- **Layers used**: Unit (20)
- **Pure functions created**: 2 (`check_one_ticket_per_user_per_category`, `check_can_edit_category`)

### Files Changed (Phase 1)

| File | Action | What Was Done |
|------|--------|---------------|
| `bot/services/ticket_invariants.py` | Modified | Added `check_one_ticket_per_user_per_category` (pure invariant) and `check_can_edit_category` (auth helper); added `Callable` import |
| `bot/core/db/ticket_db.py` | Modified | Added `count_user_open_tickets_in_category` method with guild/author/category/status filters + optional `exclude_ticket_id` neq filter |
| `tests/test_ticket_invariants.py` | Modified | Added `TestCheckOneTicketPerUserPerCategory` (7 tests) and `TestCheckCanEditCategory` (4 tests); updated imports |
| `tests/test_ticket_db.py` | Modified | Added `TestCountUserOpenTicketsInCategory` (9 tests) |
| `tests/test_database.py` | Modified | Added `neq()` method to `FakeQueryBuilder` for Supabase neq filter support |
| `openspec/changes/ticket-category-ops/tasks.md` | Modified | Marked tasks 1.1–1.7 as [x] |

---

## Phase 2: Service — create_ticket Guard + edit_ticket_category

### Status: COMPLETE (5/5 tasks)

### TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 2.1 | `tests/test_ticket_service.py` | Unit | ✅ 93/93 | ✅ Written (5 tests) | — (GREEN in 2.2) | ✅ 5 spec scenarios | ✅ Clean |
| 2.2 | `tests/test_ticket_service.py` | Unit | N/A (new) | — (RED in 2.1) | ✅ 5/5 passed | ✅ blocked, different-category, closed-frees, subticket-bypass, null-category-bypass | ✅ Clean |
| 2.3 | `tests/test_ticket_service.py` | Unit | ✅ 98/98 | ✅ Written (10 tests) | — (GREEN in 2.4) | ✅ 10 spec scenarios | ✅ Clean |
| 2.4 | `tests/test_ticket_service.py` | Unit | N/A (new) | — (RED in 2.3) | ✅ 10/10 passed | ✅ DB+rename, rename-failure, audit, mod-denied, closed-rejected, limit-violation, empty-category, exclude-ticket, same-category-noop, not-found | ✅ Clean |
| 2.5 | `tests/test_ticket_service.py` | Unit | — | — | — | — | ✅ 108/108 pass, ruff clean |

### Test Summary (Phase 2)

- **Safety net baseline**: 93 tests (existing)
- **Tests written (create_ticket guard)**: 5
  - Second ticket in same category blocked (ValueError)
  - Different category allowed (count=0, insert succeeds)
  - Closed frees slot (count=0, insert succeeds)
  - Subticket bypasses guard (count never called)
  - Null categoryId bypasses guard (count never called)
- **Tests written (edit_ticket_category)**: 10
  - DB + rename success
  - HTTPException rename failure → log warning, return rename_succeeded=False
  - Audit row on success (action=edit_category, outcome=success)
  - Non-mod denied → audit denied, no DB mutation
  - Closed ticket rejected → ValueError, no DB mutation
  - Limit violation → ValueError, no DB mutation
  - Empty category allowed (count=0)
  - exclude_ticket_id passed to count
  - Same-category no-op doesn't self-block
  - Ticket not found → ValueError
- **Total tests passing**: 108/108 (93 baseline + 15 new)
- **Layers used**: Unit (15)
- **Full test_ticket_service+invariants+db**: 188/188 pass

### Files Changed (Phase 2)

| File | Action | What Was Done |
|------|--------|---------------|
| `bot/services/ticket_service.py` | Modified | Added `check_can_edit_category` and `check_one_ticket_per_user_per_category` imports; added per-user-per-category guard in `create_ticket()` before numbering loop; added `edit_ticket_category()` method (120 lines) with closed rejection, mod auth, limit check, DB update, audit, and best-effort channel rename |
| `tests/test_ticket_service.py` | Modified | Added `count_user_open_tickets_in_category` to mock_db fixture; added 5 create_ticket guard tests + 10 edit_ticket_category tests; fixed 3 ruff RUF059 unused-variable warnings |
| `openspec/changes/ticket-category-ops/tasks.md` | Modified | Marked tasks 2.1–2.5 as [x] |

### Deviations from Design

None — implementation matches design.

> Fixed post-review (JD-A-001 / Phase 2 gate): `edit_ticket_category` now
> resolves the author via `resolve_member_safe` like `_build_reopen_channel`
> instead of hardcoding `display_name = "user"`. Test
> `test_edit_ticket_category_updates_db_and_renames` now asserts the actual
> channel name kwargs. A stale docstring note in `create_subticket` ("does
> not enforce that constraint") was corrected — `create_ticket` does enforce
> the per-user-per-category limit.

### Issues Found

None.

### Batch Boundary

- **Work unit**: PR 2 (service only)
- **Scope**: create_ticket guard + edit_ticket_category + tests
- **Excluded**: Views, i18n (Phase 3)
- **Estimated review impact**: ~200 lines changed across 3 files

---

## Phase 3: Views + i18n — Edit Button + Ephemeral Select

### Status: COMPLETE (7/7 tasks)

### TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 3.1 | N/A (i18n keys) | Structural | N/A | — | — | — | ✅ Valid JSON |
| 3.2 | N/A (i18n keys) | Structural | N/A | — | — | — | ✅ Valid JSON |
| 3.3 | `tests/test_ticket_views.py` | Unit | ✅ 38/38 | ✅ Written (12 tests) | — (GREEN in 3.4–3.5) | ✅ 12 spec scenarios | ✅ Clean |
| 3.4 | `tests/test_ticket_views.py` | Unit | N/A (new) | — (RED in 3.3) | ✅ 5/5 passed | ✅ button-exists, i18n-label, non-mod-rejected, mod-shows-select, no-categories | ✅ ruff clean |
| 3.5 | `tests/test_ticket_views.py` | Unit | N/A (new) | — (RED in 3.3) | ✅ 7/7 passed | ✅ non-mod-re-submit, closed-reject, calls-service, limit-ux, rename-warning, success, timeout-300 | ✅ ruff clean |
| 3.6 | `tests/test_ticket_views.py` | Unit | — | — | — | — | ✅ Covered by 3.4 i18n-label test |
| 3.7 | `tests/test_ticket_views.py` | Unit | — | — | — | — | ✅ 50/50 pass, ruff clean |

### Test Summary (Phase 3)

- **Safety net baseline**: 38 tests (existing view tests)
- **Tests written (TestEditCategoryButton)**: 5
  - Button exists with `custom_id="ticket:edit-category"` and secondary style
  - Button label resolved via `t("tickets.actions.edit_category_button")` at init
  - Non-mod click → ephemeral rejection embed
  - Mod click → ephemeral `_EditCategoryView` with categories
  - No active categories → ephemeral no-categories message (no view)
- **Tests written (TestEditCategorySelect)**: 7
  - Non-mod re-check on submit → rejected, no service call
  - Closed ticket → rejected, no service call
  - Valid selection → `edit_ticket_category()` called with `is_mod=True`
  - ValueError → specific `edit_category_limit_*` keys (NOT `creation_failed`)
  - `rename_succeeded=False` → success embed with rename warning appended
  - Successful edit → ephemeral success embed
  - `_EditCategoryView` timeout = 300s
- **Total tests passing**: 50/50 (38 baseline + 12 new)
- **Layers used**: Unit (12)
- **Full ticket test suite**: 238/238 pass (service+invariants+db+views)

### Files Changed (Phase 3)

| File | Action | What Was Done |
|------|--------|---------------|
| `bot/locales/en.json` | Modified | Added 10 i18n keys under `tickets.actions`: `edit_category`, `edit_category_button`, `edit_category_success`, `edit_category_success_description`, `edit_category_rename_warning`, `edit_category_limit_title`, `edit_category_limit_description`, `edit_category_closed_title`, `edit_category_closed_description`, `edit_category_mods_only_title`, `edit_category_mods_only_description`, `edit_category_no_categories_title`, `edit_category_no_categories_description` |
| `bot/locales/es.json` | Modified | Added corresponding 13 Spanish translations |
| `bot/views/tickets.py` | Modified | Added persistent `edit_category_button` (`custom_id="ticket:edit-category"`, secondary style) to `TicketActionsView`; added `_EditCategoryView` (timeout=300) and `_EditCategorySelect` with mod re-check, closed rejection, `edit_ticket_category()` delegation, specific limit UX, rename warning, and success confirmation; updated `__init__` to resolve edit button label via `t()` |
| `tests/test_ticket_views.py` | Modified | Added `TestEditCategoryButton` (5 tests) and `TestEditCategorySelect` (7 tests) with mock helpers for interaction, ticket row, category rows, and select construction |
| `openspec/changes/ticket-category-ops/tasks.md` | Modified | Marked tasks 3.1–3.7 as [x] |

### Deviations from Design

None — implementation matches design.

### Issues Found

None.

### Batch Boundary

- **Work unit**: PR 3 (views + i18n only)
- **Scope**: Edit Category button, ephemeral select, i18n keys, view tests
- **Excluded**: Foundation invariants, DB query, service (Phases 1–2)
- **Estimated review impact**: ~180 lines changed across 4 files

---

## Phase 4: Final Verification

### Status: COMPLETE (2/2 tasks)

### Verification Results

| Check | Tool | Result |
|-------|------|--------|
| 4.1 Full suite | `uv run pytest` | ✅ 1423 passed, 3 skipped, 0 failed (88% coverage) |
| 4.2 Syntax | `python -m py_compile bot/__main__.py` | ✅ No errors |
| Ruff | `ruff check` on changed Python files | ✅ All checks passed |
| Mypy | `mypy` on changed Python files | ✅ Success: no issues found |

### Bugs Found and Fixed During Verification

| Bug | Location | Fix |
|-----|----------|-----|
| `confirm_view.message` dedented outside `if claimed_by_id:` block — `UnboundLocalError` on unclaimed tickets | `bot/views/tickets.py:507` | Re-indented into `if` block + restored the direct-claim `else` path |
| `guild_id` and `guild` not narrowed before `get_ticket_categories()` / `_EditCategoryView()` — mypy `arg-type` | `bot/views/tickets.py:667,688` | Added `guild is None or guild_id is None` guard to early return |
| `interaction.channel` not narrowed to `TextChannel` for `edit_ticket_category()` — mypy `arg-type` | `bot/views/tickets.py:838` | Added `isinstance(channel, discord.TextChannel)` guard |

### Files Changed (Phase 4)

| File | Action | What Was Done |
|------|--------|---------------|
| `bot/views/tickets.py` | Modified | Fixed claim_button indentation bug; added type-narrowing guards in `edit_category_button` and `_EditCategorySelect.callback` |
| `openspec/changes/ticket-category-ops/tasks.md` | Modified | Marked tasks 4.1–4.2 as [x] |

---

## Cumulative Summary

- **Phases complete**: 4/4 (Phase 1 foundation + Phase 2 service + Phase 3 views+i18n + Phase 4 verification)
- **Total tests written across all phases**: 47 (20 Phase 1 + 15 Phase 2 + 12 Phase 3)
- **Total tests passing**: 1423/1423 (full project suite, 3 skipped)
- **Coverage**: 88%
- **Pure functions created**: 2 (invariants)
- **Service methods added**: 1 (`edit_ticket_category`)
- **Service methods modified**: 1 (`create_ticket` — guard added)
- **View components added**: 3 (`edit_category_button`, `_EditCategoryView`, `_EditCategorySelect`)
- **i18n keys added**: 26 (13 en + 13 es)
- **Verification bugs fixed**: 3 (claim_button indentation, type-narrowing guards)

---

## Post-Verification Surgical Fix: R3-001

### Status: COMPLETE

### Defect

`_EditCategorySelect.callback` in `bot/views/tickets.py` had two reliability
holes in the edit-category submit path:

1. **Stale closed check** — the callback read `self._ticket_row`, captured
   when the Edit Category button was clicked, to decide if the ticket was
   closed. During the 300s ephemeral dropdown window the ticket could be
   closed by another staff member, and the stale row would pass the gate.
2. **Blanket `except ValueError`** — every `ValueError` from
   `edit_ticket_category` was routed to the `edit_category_limit_*` UX, so a
   closed-ticket error (or any other service error) surfaced as the
   misleading "limit reached" message.

### Fix

`bot/views/tickets.py` (`_EditCategorySelect.callback`):

- Removed the stale `ticket_row = self._ticket_row` read in favour of a
  fresh `bot.db.get_ticket_by_channel(str(channel.id))` re-fetch on submit,
  mirroring `_get_ticket` / the close button path. Both the DB-`None` and
  status==`"closed"` branches show `edit_category_closed_*` keys; the service
  is never invoked on a ticket the DB reports closed (or missing).
- Replaced the blanket `except ValueError` with message-based
  classification of the descriptive service exception:
  - message contains `"closed"` → `edit_category_closed_*` keys
  - message contains `"already has an open"` (the real
    `check_one_ticket_per_user_per_category` invariant text) →
    `edit_category_limit_*` keys
  - otherwise → generic `error_embed` with
    `common.error.unexpected_title` + `str(exc)` — **NOT** the limit keys.

`tests/test_ticket_views.py` (`TestEditCategorySelect`):

- Updated `test_select_limit_violation_shows_specific_ux` to use the real
  invariant message (`"User ... already has an open ticket in category ..."`).
- Added `test_select_closed_during_dropdown_window_is_rejected`: select
  built with a stale OPEN row, DB now reports CLOSED → closed UX, no service
  call.
- Added `test_select_service_closed_valueerror_shows_closed_ux`: DB row open
  (race) but service raises the closed `ValueError` → closed keys, NOT limit
  keys.
- Added `test_select_other_valueerror_does_not_show_limit_ux`: a
  not-found `ValueError` → `common.error.unexpected_title` + `str(exc)`,
  never the limit keys.

### Verification

| Check | Command | Result |
|-------|---------|--------|
| View tests | `uv run pytest tests/test_ticket_views.py --no-cov -q` | ✅ 53 passed |
| Lint | `uv run ruff check bot/views/tickets.py tests/test_ticket_views.py` | ✅ All checks passed |

### Files Changed (R3-001)

| File | Action | What Was Done |
|------|--------|---------------|
| `bot/views/tickets.py` | Modified | Re-fetch ticket from DB on select submit; map `ValueError` by message (closed / limit / generic) instead of blanket limit UX |
| `tests/test_ticket_views.py` | Modified | Updated limit test to real invariant message; added 3 tests for closed-during-window, service-closed `ValueError`, and other `ValueError` |
