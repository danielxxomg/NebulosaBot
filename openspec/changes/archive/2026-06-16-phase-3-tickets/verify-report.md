# Verification Report: Phase 3 — Tickets (after fixes)

**Change**: phase-3-tickets  
**Version**: after-fixes  
**Mode**: Standard (`strict_tdd: false`)  
**Verified**: 2026-06-16  
**Verifier**: sdd-verify executor  

---

## Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 18 |
| Tasks checked | 18 |
| Tasks with objective evidence | 17 |

All tasks in `tasks.md` are now marked `[x]`. **Task 1.6** is checked, but the expected test file `tests/test_ticket_category.py` does not exist on disk, so it is treated as incomplete for archive readiness.

---

## Build & Tests Execution

**Build**: ✅ Passed (modules import cleanly, pytest collects 67 items)

**Tests**: ✅ 67 passed / ❌ 0 failed / ➖ 0 skipped

```text
$ uv run pytest -q
...................................................................      [100%]
67 passed in 2.16s
```

**Coverage**: ➖ Not available (`pytest-cov` not installed)

> No new tests were added for the six code fixes, so the test count is unchanged.

---

## Fixes Verified

| Fix | Location | Status | Evidence |
|-----|----------|--------|----------|
| Already-claimed guard | `bot/cogs/tickets.py` lines 167–177 | ✅ Implemented correctly | Rejects claim with error embed when `claimedBy` is set |
| Duplicate category name guard | `bot/cogs/tickets.py` lines 898–908 | ✅ Implemented correctly | Case-insensitive name check against existing categories before insert |
| Delete-with-open-tickets guard | `bot/cogs/tickets.py` lines 1059–1082 | ✅ Implemented correctly | Uses `Database.count_open_tickets_by_category()` and rejects if > 0 |
| `order` → `position` alignment | Migration, model, DB layer, `openspec/specs/ticket-category-model/spec.md` | ✅ Aligned | Column/field/spec consistently use `position` |
| Silent auto-close | `bot/cogs/tickets.py` `_close_one_ticket()` lines 710–735 | ✅ Implemented correctly | No channel notification before delete; only logs |
| Tasks 1.6, 4.1, 4.2, 4.3 marked complete | `openspec/changes/phase-3-tickets/tasks.md` | ⚠️ Checked, but 1.6 lacks artifact | See CRITICAL issue #1 |

---

## Spec Compliance Matrix

| Requirement | Scenario | Test / Evidence | Result |
|-------------|----------|-----------------|--------|
| **Ticket Service** |
| REQ-01 Ticket creation | Successful creation | `tests/test_ticket_service.py::test_create_ticket_normal` | ✅ COMPLIANT |
| REQ-01 Ticket creation | Sequential numbering | `tests/test_ticket_service.py::test_create_ticket_normal` (MAX 41 → 42) | ✅ COMPLIANT |
| REQ-01 Ticket creation | Race condition retry | `tests/test_ticket_service.py::test_create_ticket_retry_on_conflict` | ✅ COMPLIANT |
| REQ-02 Ticket claim | Staff claims ticket | `tests/test_ticket_service.py::test_claim_ticket_updates_status` | ✅ COMPLIANT |
| REQ-02 Ticket claim | Already claimed | Static: `TicketActionsView.claim_button` rejects when `claimedBy` set | ⚠️ PARTIAL (no covering test) |
| REQ-03 Ticket close | Close with transcript | Static: `close_button` generates/upload transcript; test only mocks URL | ⚠️ PARTIAL (no integration test) |
| REQ-03 Ticket close | Close unclaimed ticket | `tests/test_ticket_service.py::test_close_ticket_updates_status` | ✅ COMPLIANT |
| REQ-04 Auto-close stale | Stale ticket | Static: `_close_one_ticket` deletes silently after 48 h cutoff | ⚠️ PARTIAL (no task-level runtime test) |
| REQ-04 Auto-close stale | Active ticket | Static: `get_stale_tickets` filters by `lastActivity` | ⚠️ PARTIAL (no explicit test) |
| **Ticket Views** |
| REQ-01 Panel view | Panel render | Static: `TicketPanelView` + `_CategorySelectView` in `tickets.py` | ⚠️ PARTIAL (no UI test) |
| REQ-01 Panel view | Open ticket from panel | Static: `_CategorySelect.callback` creates channel + DB record | ⚠️ PARTIAL (no UI test) |
| REQ-01 Panel view | Empty category list | Static: returns ephemeral error instead of disabled dropdown | ⚠️ PARTIAL (behavior differs from spec) |
| REQ-02 Action view | Action view render | Static: welcome message sent with `TicketActionsView()` | ⚠️ PARTIAL (no UI test) |
| REQ-02 Action view | Close from action view | Static: `close_button` triggers full close flow | ⚠️ PARTIAL (no UI test) |
| REQ-02 Action view | Claim from action view | Static: `claim_button` triggers claim flow + guard | ⚠️ PARTIAL (no UI test) |
| REQ-03 View persistence | Bot restart | Static: `bot.add_view(TicketPanelView/TicketActionsView)` in `setup_hook()` | ⚠️ PARTIAL (no runtime restart test) |
| **Transcript Service** |
| REQ-01 HTML generation | Generate transcript | `tests/test_transcript_service.py::test_generate_produces_html` | ✅ COMPLIANT |
| REQ-01 HTML generation | Cap message count | `tests/test_transcript_service.py::test_generate_respects_message_cap` | ✅ COMPLIANT |
| REQ-02 Transcript upload | Successful upload | `tests/test_transcript_service.py::test_upload_returns_attachment_url` | ✅ COMPLIANT |
| REQ-02 Transcript upload | Log channel missing | Static: `close_button` / `_close_one_ticket` skip upload when no log channel | ⚠️ PARTIAL (no test) |
| REQ-03 Transcript content | Rich content (attachments/embeds) | Static: only author/timestamp/text rendered | ❌ NOT IMPLEMENTED (SHOULD-level) |
| **Ticket Commands** |
| REQ-01 Ticket panel command | Deploy panel | Static: `/ticket_panel` sends embed + view and persists IDs | ⚠️ PARTIAL (no test) |
| REQ-01 Ticket panel command | Insufficient permissions | Static: `@is_mod()` decorator present | ⚠️ PARTIAL (no test) |
| REQ-02 Create category command | Create category | Static: `/create_category` inserts with position | ⚠️ PARTIAL (no test) |
| REQ-02 Create category command | Duplicate name | Static: case-insensitive name check in command | ⚠️ PARTIAL (no covering test) |
| REQ-03 List categories command | List categories | Static: `/list_categories` queries by guild ordered by position | ⚠️ PARTIAL (no test) |
| REQ-04 Delete category command | Delete existing category | Static: `/delete_category` hard-deletes after validation | ⚠️ PARTIAL (no test) |
| REQ-04 Delete category command | Delete with open tickets | Static: open-ticket count guard | ⚠️ PARTIAL (no covering test) |
| **Ticket Category Model** |
| REQ-01 Dataclass fields | Build from row | Model exists; no test file | ⚠️ PARTIAL / ❌ TASK 1.6 MISSING |
| REQ-02 Guild-scoped CRUD | Create category | `Database.insert_ticket_category()` | ✅ STATIC |
| REQ-02 Guild-scoped CRUD | List by guild | `Database.get_ticket_categories()` orders by `position` | ✅ STATIC |
| REQ-02 Guild-scoped CRUD | Duplicate name within guild | Application-level check in command | ⚠️ PARTIAL (no DB constraint) |
| REQ-03 Positioning | Position increment | Default position is `999`, not next available integer | ❌ NOT IMPLEMENTED |
| **Delta: Initial Schema** |
| REQ-01 Migration 002 | Run migration 002 | `migrations/002_ticket_categories.sql` exists | ✅ STATIC |
| REQ-02 Ticket category table | Ticket category insert | Migration creates table with required + extra fields | ✅ STATIC |
| REQ-03 Ticket category indexes | Query categories by guild | Only single-column `idx_ticket_category_guild` present; composite `(guildId, position)` missing | ⚠️ PARTIAL |
| REQ-04 Guild table (modified) | Guild insert | `ticketPanelMessageId` / `ticketPanelChannelId` added | ✅ COMPLIANT |
| **Delta: Guild Config** |
| REQ-01 Panel persistence fields | Panel deployment persisted | `Database.update_guild_panel()` called from `/ticket_panel` | ⚠️ PARTIAL (GuildService cache not invalidated) |
| REQ-01 Panel persistence fields | Panel lookup on startup | `bot.add_view()` registers persistent views | ⚠️ PARTIAL (does not fetch panel message) |
| REQ-01 Panel persistence fields | Missing panel message | Not implemented | ❌ UNTESTED / NOT IMPLEMENTED |

**Compliance summary**: 7/40 scenarios compliant with runtime evidence; 26 scenarios implemented but only statically or partially verified; 4 scenarios not implemented/untested.

---

## Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| TicketService implemented | ✅ Implemented | `create_ticket`, `close_ticket`, `claim_ticket`, `get_stale_tickets`, channel cache |
| TranscriptService implemented | ✅ Implemented | `generate` and `upload` with HTML escaping and cap |
| TicketCategory model implemented | ✅ Implemented | `TicketCategory` dataclass with `from_db_row()`/`to_db_dict()`; extra `emoji`/`active` fields do not break required fields |
| Ticket commands implemented | ✅ Implemented | `/ticket_panel`, `/create_category`, `/list_categories`, `/delete_category` gated by `@is_mod()` |
| Persistent views implemented | ✅ Implemented | `TicketPanelView` (`custom_id="ticket:open"`) and `TicketActionsView` (`custom_id="ticket:claim"` / `"ticket:close"`) with `timeout=None` |
| Auto-close task implemented | ✅ Implemented | `@tasks.loop(hours=1)` `auto_close_stale_tickets` with 48 h cutoff and silent close |
| `on_message` listener implemented | ✅ Implemented | O(1) cache check then `update_ticket_last_activity()` |
| Guild panel columns added | ✅ Implemented | `bot/models/guild.py` includes `ticket_panel_message_id` / `ticket_panel_channel_id` and aliases |
| Bot wiring complete | ✅ Implemented | `bot/bot.py` initialises services, registers views, loads `bot.cogs.tickets` |
| Migration 002 present | ✅ Implemented | `migrations/002_ticket_categories.sql` creates `ticket_category` table and guild panel columns |
| Already-claimed guard | ✅ Fixed | View checks `claimedBy` before allowing claim |
| Duplicate category name guard | ✅ Fixed | Command checks existing names before insert |
| Delete-with-open-tickets guard | ✅ Fixed | Command uses new `count_open_tickets_by_category()` DB method |
| Auto-close silent | ✅ Fixed | `_close_one_ticket` no longer sends a visible channel embed |

---

## Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| Sequential numbering: MAX+1 with 3 retries | ✅ Yes | `TicketService.create_ticket` retry loop; `MAX_RETRIES = 3` |
| Panel persistence: guild table columns | ✅ Yes | `ticketPanelMessageId` / `ticketPanelChannelId` added to `guild` |
| Transcript format: inline-CSS HTML | ✅ Yes | `transcript_service.py` generates self-contained HTML |
| `on_message` perf: cached `set[int]` | ✅ Yes | `_ticket_channel_cache` + `is_ticket_channel()` O(1) lookup |
| Auto-close: hourly loop + silent close | ✅ Yes | `@tasks.loop(hours=1)` used; no channel notification on auto-close |

Design deviations observed:

- `create_category` accepts a `position` argument (default `999`) and does not auto-assign the next available position. The `ticket-category-model` spec requires new categories to receive the next integer (0,1,2 → 3).
- `TicketActionsView` uses a fresh view instance per welcome message. This is acceptable for discord.py persistent views but differs slightly from the design text.

---

## Issues Found

### CRITICAL

1. **Task 1.6 missing artifact** — `tasks.md` marks task 1.6 complete, but `tests/test_ticket_category.py` does not exist. The expected round-trip test for `TicketCategory.from_db_row()`/`to_db_dict()` was not added.
2. **TicketCategory position auto-increment not implemented** — `openspec/specs/ticket-category-model/spec.md` REQ-03 requires a new category to receive the next available position. `/create_category` defaults `position=999` and never computes the next integer.
3. **No covering tests for the new guards** — The already-claimed, duplicate-name, and delete-with-open-tickets scenarios are implemented in code but have no unit tests. Under the spec-driven contract, a scenario is only proven compliant when a covering test passes at runtime.

### WARNING

1. **Large untested command/view surface** — Panel deployment, category CRUD commands, ticket views, and integration flows remain without automated tests.
2. **Panel persistence does not invalidate cache** — `update_guild_panel()` writes to the DB, but `GuildService` cache is not refreshed.
3. **Missing panel-message cleanup on startup** — The "missing panel message" scenario (clear stale IDs and log warning) is not implemented.
4. **Transcript does not render attachments/embeds** — The SHOULD-level "Rich content" scenario is not satisfied; only author, timestamp, and text content are rendered.
5. **Composite ticket_category index missing** — `migrations/002_ticket_categories.sql` creates only `idx_ticket_category_guild`; the spec SHOULD index is `(guildId, position)`.
6. **Duplicate-name guard is application-only** — No DB unique constraint on `(guildId, name)`, so a race could allow duplicates.
7. **Tasks artifact still mentions `order`** — Line 29 of `tasks.md` describes the table with `"order"`, while the rest of the design/specs/migration use `position`.

### SUGGESTION

1. Add `tests/test_ticket_category.py` with a round-trip test and a position test to close task 1.6.
2. Add unit tests for the three new guards (`claim` already claimed, `create_category` duplicate name, `delete_category` with open tickets).
3. Implement position auto-increment in `/create_category` (or document the decision if `position=999` is intentional).
4. Add a unique partial index on `ticket_category ("guildId", name)` where `active = true` to harden duplicate-name rejection.
5. Add the composite index `idx_ticket_category_guild_position` on `("guildId", "position")`.

---

## Verdict

**FAIL**

The six listed code fixes are correctly implemented and there are no test regressions (67/67 pass). However, the change still cannot be archived because:

- Task 1.6 is marked complete but the required test file is missing.
- A required spec scenario (`ticket-category-model` position increment) is not implemented.
- The new guard scenarios lack runtime test coverage.

Address the CRITICAL issues and add covering tests before re-running verification.
