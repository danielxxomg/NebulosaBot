# Tasks: Ticket Panel Persistence After Bot Restart

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 370–420 |
| 400-line budget risk | Medium |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: stacked-to-main
400-line budget risk: Medium

## Phase 1: DB + Service Layer (Foundation)

- [x] 1.1 RED `tests/test_database.py`: test `update_guild_panel()` calls `_on_write` hook after successful update
- [x] 1.2 GREEN `bot/core/db/guild_db.py`: add `self._on_write` call to `update_guild_panel()` after execute; support nullable `message_id`/`channel_id` for clearing
- [x] 1.3 RED `tests/test_guild_service.py`: test `update_guild_panel()` invalidates `{guild_id}:config` cache after DB write
- [x] 1.4 RED `tests/test_guild_service.py`: test `update_guild_panel()` does NOT invalidate cache if DB write fails
- [x] 1.5 GREEN `bot/services/guild_service.py`: add `async def update_guild_panel(guild_id, message_id, channel_id)` — calls `guild_db.update_guild_panel()`, then `cache.invalidate()` on success

## Phase 2: Shared Deploy Helper (Core)

- [x] 2.1 RED `tests/test_ticket_views.py`: test `deploy_ticket_panel()` sends embed+view, returns message, calls `update_guild_panel`
- [x] 2.2 RED `tests/test_ticket_views.py`: test `deploy_ticket_panel()` raises on `Forbidden`
- [x] 2.3 GREEN `bot/views/tickets.py`: extract `deploy_ticket_panel(channel, guild_id, *, title, description)` — builds embed, sends with `TicketPanelView`, calls `GuildService.update_guild_panel()`, returns message

## Phase 3: Startup Validation (Integration)

- [x] 3.1 RED `tests/test_bot.py`: test healthy panel — `fetch_message` succeeds with `ticket:open` button → no re-deploy
- [x] 3.2 RED `tests/test_bot.py`: test deleted panel — `fetch_message` raises `NotFound` → re-deploy + update IDs
- [x] 3.3 RED `tests/test_bot.py`: test stripped panel — message exists but no `ticket:open` button → re-deploy
- [x] 3.4 RED `tests/test_bot.py`: test missing channel — `get_channel` returns `None` → clear IDs + log warning
- [x] 3.5 RED `tests/test_bot.py`: test `Forbidden` on fetch → skip guild + log warning
- [x] 3.6 RED `tests/test_bot.py`: test validation runs AFTER backfill gather completes
- [x] 3.7 GREEN `bot/bot.py`: add `_validate_panels()` method — bounded `asyncio.gather()` over guilds with stored `ticket_panel_message_id`; check `ticket:open` custom_id in components; call `deploy_ticket_panel()` on unhealthy; call `guild_service.update_guild_panel()` or clear IDs on missing channel
- [x] 3.8 GREEN `bot/bot.py`: call `_validate_panels()` at end of `on_ready()`, after backfill gather

## Phase 4: Cog Wiring + Docs

- [x] 4.1 GREEN `bot/cogs/tickets.py`: replace inline embed+send+`update_guild_panel` in `ticket_panel` command with call to `deploy_ticket_panel()` helper
- [x] 4.2 REFACTOR: verify `/ticket_panel` still works — same embed, same persistence, same error handling
- [x] 4.3 GREEN `docs/MANUAL.md`: remove ticket-panel restart debt row

## Phase 5: Verify

- [x] 5.1 Run `uv run pytest` — all tests pass (baseline: 1146 passed, 3 skipped)
- [x] 5.2 Verify no new warnings introduced
