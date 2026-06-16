# Tasks: Phase 3 — Tickets Module

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~795 (6 new files + 3 modified) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (Foundation) → PR 2 (Services + Tests) → PR 3 (Cog + Wiring) |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | DB schema + model + CRUD layer | PR 1 | Base: feature/phase-3-tickets; ~210 lines; tests for model round-trip |
| 2 | TicketService + TranscriptService + unit tests | PR 2 | Base: PR 1 branch; ~370 lines; depends on PR 1 DB methods |
| 3 | TicketsCog + bot.py wiring + integration verification | PR 3 | Base: PR 2 branch; ~215 lines; depends on PR 2 services |

## Phase 1: Foundation — Schema, Model & Database

- [x] 1.1 Create `migrations/002_ticket_categories.sql`: `ticket_category` table (id, guildId, name, description, "order", createdAt) + add `ticketPanelMessageId` and `ticketPanelChannelId` nullable columns to `guild`
- [x] 1.2 Create `bot/models/ticket_category.py`: `TicketCategory` dataclass with `from_db_row()`/`to_db_dict()` following `Ticket` pattern
- [x] 1.3 Modify `bot/models/guild.py`: add `ticket_panel_message_id: str | None` and `ticket_panel_channel_id: str | None` fields; update `from_db_row()`, `to_db_dict()`, and `_db_aliases`
- [x] 1.4 Add ticket CRUD to `bot/core/database.py`: `insert_ticket()`, `update_ticket()`, `get_ticket_by_channel()`, `get_max_ticket_number(guild_id)`, `get_stale_tickets(cutoff)`
- [x] 1.5 Add category CRUD to `bot/core/database.py`: `insert_ticket_category()`, `get_ticket_categories(guild_id)`, `delete_ticket_category()`, `update_guild_panel()`
- [ ] 1.6 Write round-trip test for `TicketCategory.from_db_row()`/`to_db_dict()` in `tests/test_ticket_category.py`

## Phase 2: Core Services & Tests

- [ ] 2.1 Create `bot/services/ticket_service.py`: `TicketService` with `__slots__`, `create_ticket()` (MAX+1 with 3-retry), `close_ticket()`, `claim_ticket()`, `_ticket_channel_cache: set[int]`, `sync_channel_cache()`
- [ ] 2.2 Create `bot/services/transcript_service.py`: `TranscriptService` with `generate(channel, limit=5000) → discord.File` (inline-CSS HTML) and `upload(file, log_channel) → str | None`
- [ ] 2.3 Create `tests/test_ticket_service.py`: test sequential numbering (normal + retry on conflict), `create_ticket` flow (mock DB + guild), `close_ticket` (mock transcript + DB), `claim_ticket` (status/claimedBy), cache sync
- [ ] 2.4 Verify: all tests pass with `pytest tests/test_ticket_service.py`

## Phase 3: Cog, Views & Bot Wiring

- [ ] 3.1 Create `bot/cogs/tickets.py` — `TicketPanelView` (timeout=None, custom_id="ticket:panel", category Select + open button) and `TicketActionsView` (timeout=None, custom_id="ticket:actions:{channel_id}", close/claim buttons)
- [ ] 3.2 Add slash commands to `TicketsCog`: `/ticket_panel` (deploy panel, persist IDs), `/create_category`, `/list_categories`, `/delete_category` — all with `app_commands.check()` for mod permission
- [ ] 3.3 Add `auto_close_stale_tickets` task (`@tasks.loop(hours=1)`) and `on_message` listener (cached channel set O(1) early exit → DB update `lastActivity`) to `TicketsCog`
- [ ] 3.4 Modify `bot/bot.py`: add `ticket_service` + `transcript_service` to `__slots__`; init in `setup_hook()`; register persistent views; load `bot.cogs.tickets` extension
- [ ] 3.5 Verify: bot starts without errors, views register, slash commands appear in tree

## Phase 4: Integration Verification

- [ ] 4.1 Verify end-to-end: panel deploy → ticket create → claim → close with transcript → channel deleted
- [ ] 4.2 Verify auto-close: mock stale ticket → task fires → close flow executes
- [ ] 4.3 Verify persistence: restart bot → views still respond to interactions
