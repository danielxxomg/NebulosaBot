# Tasks: Cache Sync Realtime

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~775-865 (bot +250 add / +250 test / -280 delete; dashboard -85) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → Migration + Realtime subscriber + tests; PR 2 → Remove webhook + dashboard cleanup |
| Delivery strategy | auto-forecast |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Migration + Realtime subscriber core + tests | PR 1 | feat(realtime): add Supabase CDC subscriber replacing webhook. ~500 lines. |
| 2 | Remove webhook code + dashboard cleanup + env cleanup | PR 2 | refactor(webhook): remove webhook capability and dashboard sync. ~365 lines. Depends on PR 1 merged. |

---

## Phase 1: Migration (prerequisite)

- [x] 1.1 Write idempotent migration SQL: check `pg_publication_tables` for existing entries before `ALTER PUBLICATION supabase_realtime ADD TABLE guild, greeting_config, ticket, ticket_note;`. Run via Supabase MCP `apply_migration`. **Verify**: query returns 4 tables.

## Phase 2: RED — Realtime subscriber tests (`tests/test_realtime.py`)

- [x] 2.1 RED: subscriber lifecycle — `test_start_creates_client_and_subscribes` (mock `acreate_client`, assert `channel("cache-sync")` created, 4x `on_postgres_changes` called, `subscribe(on_subscribe)` awaited)
- [x] 2.2 RED: `test_stop_removes_channel_and_closes_client` — assert `remove_channel`, `remove_all_channels`, client `close()` called in order
- [x] 2.3 RED: CDC handler dispatch — parametrized tests for each table: `guild`→`record["id"]`, `greeting_config`→`record["guildId"]`, `ticket`→`record["guildId"]`, `ticket_note`→resolve via ticket query. Each asserts `cache.invalidate_guild()` called with correct guild_id.
- [x] 2.4 RED: `test_delete_event_uses_old_record` — payload with `type="DELETE"`, empty `record`, valid `old_record`; assert `old_record` identifiers used.
- [x] 2.5 RED: self-echo filtering — `test_recent_write_skips_invalidation`: mark `(guild, G)`, fire CDC, assert `invalidate_guild` NOT called. `test_expired_write_allows_invalidation`: advance time >5s, assert called. `test_unrelated_write_still_invalidates`: mark different table, assert called.
- [x] 2.6 RED: health check — `test_health_logs_subscribed_status`: mock status `SUBSCRIBED`, assert debug log. `test_health_warns_on_channel_error`: mock `CHANNEL_ERROR` >60s, assert warning + fallback enabled.
- [x] 2.7 RED: poll fallback — `test_poll_queries_ticket_lastActivity`: mock DB response with guild IDs, assert `invalidate_guild` called per guild. `test_poll_scans_all_guilds`: assert full table scan for config tables. `test_poll_stops_on_recovery`: mock status→`SUBSCRIBED`, assert poll loop cancelled.
- [x] 2.8 RED: migration watchdog — `test_watchdog_warns_after_30s_no_events`: subscribe, advance 30s with zero CDC events, assert warning logged.
- [x] 2.9 Verify RED: run `uv run pytest tests/test_realtime.py -v` — all new tests FAIL.

## Phase 3: GREEN — Implement `bot/core/realtime.py`

- [x] 3.1 GREEN: create `RecentWriteSet` class — `asyncio.Lock`-guarded `dict[str, float]`, `mark(table, identifier)` and `contains(table, identifier)` with lazy 5s TTL eviction.
- [x] 3.2 GREEN: create `TicketGuildCache` — `ticket_id → (guild_id, expires_at)` TTL mapping for `ticket_note` resolution.
- [x] 3.3 GREEN: create `RealtimeCacheSubscriber` — constructor takes `supabase_url`, `supabase_key`, `TTLCache`, optional client factory. `start()`: `acreate_client`, `channel("cache-sync")`, 4x `on_postgres_changes(event="*", schema="public", table=...)`, `channel.subscribe(on_subscribe)`.
- [x] 3.4 GREEN: implement `on_subscribe(status, err)` callback — store status/timestamp, log, disable fallback on `SUBSCRIBED`.
- [x] 3.5 GREEN: implement CDC handler dispatch — route by `table` field, extract identifiers from `record`/`old_record`, call `cache.invalidate_guild()`, store ticket→guild mapping. Handle `ticket_note` via cache then Supabase lookup fallback.
- [x] 3.6 GREEN: implement `_health_loop` — 60s `asyncio.Task`, log status, enable poll fallback after >60s non-SUBSCRIBED, disable on recovery.
- [x] 3.7 GREEN: implement `_poll_loop` — 30s `asyncio.Task`, ticket incremental query (`lastActivity` window), guild+greeting_config full scan. Stop on recovery, reset `last_check`.
- [x] 3.8 GREEN: implement `_migration_watchdog` — 30s after first SUBSCRIBED, warn if zero CDC events received.
- [x] 3.9 GREEN: implement `stop()` — cancel health/poll/watchdog tasks, `remove_channel`, `remove_all_channels`, best-effort `close()`.
- [x] 3.10 GREEN: implement `mark_recent_write(table, identifier)` — public API for database.py integration.
- [x] 3.11 Verify GREEN: `uv run pytest tests/test_realtime.py -v` — all pass.

## Phase 4: Wire subscriber (`bot/core/database.py` + `bot/bot.py`)

- [x] 4.1 RED: `test_setup_hook_starts_subscriber` — mock `RealtimeCacheSubscriber`, assert `start()` called after cache init. `test_close_stops_subscriber` — assert `stop()` called before `super().close()`.
- [x] 4.2 GREEN: add async client factory to `bot/core/database.py` — `acreate_client` import and helper function.
- [x] 4.3 GREEN: modify `bot/bot.py` — replace `_webhook_runner` with `_realtime_subscriber` in `__slots__`, create subscriber in `setup_hook()`, call `start()`, call `stop()` in `close()`.
- [x] 4.4 Verify: `uv run pytest tests/test_bot.py -v` — lifecycle tests pass.

## Phase 5: Remove webhook code

- [ ] 5.1 RED: `test_webhook_config_removed` — assert `BotConfig` has no `webhook_secret`, `webhook_host`, `webhook_port`, `WEBHOOK_DEFAULT_HOST`, `WEBHOOK_DEFAULT_PORT` attributes.
- [ ] 5.2 RED: `test_no_webhook_server_in_setup` — assert `setup_hook` does not start aiohttp runner.
- [ ] 5.3 GREEN: delete `bot/webhook/server.py`, `bot/webhook/auth.py`, `bot/webhook/models.py`, `bot/webhook/__init__.py`.
- [ ] 5.4 GREEN: remove webhook fields and defaults from `bot/config.py`.
- [ ] 5.5 GREEN: remove webhook server start/stop from `bot/bot.py` (if not already removed in Phase 4).
- [ ] 5.6 GREEN: delete `tests/test_webhook_server.py`, `tests/test_webhook_auth.py`, `tests/test_webhook_models.py`.
- [ ] 5.7 Verify: `uv run pytest -v` — no webhook tests exist, all remaining pass.

## Phase 6: Dashboard cleanup

- [ ] 6.1 RED: assert `notifyWebhookSync` import removed from `dashboard/lib/actions/guild-actions.ts`, `economy-actions.ts`, `greeting-actions.ts`. Assert actions still succeed.
- [ ] 6.2 GREEN: delete `dashboard/lib/webhook-sync.ts` and `dashboard/__tests__/lib/webhook-sync.test.ts`.
- [ ] 6.3 GREEN: remove `notifyWebhookSync()` calls and imports from 3 action files.
- [ ] 6.4 Verify: `npm run test` — dashboard tests pass.

## Phase 7: Env + app.py cleanup

- [ ] 7.1 GREEN: simplify `app.py` to bot-only (<20 lines): dotenv, logging, import `bot.__main__.main`, `asyncio.run()`. Remove cloudflared, aiohttp imports.
- [ ] 7.2 GREEN: remove `WEBHOOK_SECRET`, `WEBHOOK_HOST`, `WEBHOOK_PORT`, `TUNNEL_TOKEN` from `.env.example`.
- [ ] 7.3 GREEN: remove `WEBHOOK_URL`, `WEBHOOK_SECRET` from `dashboard/.env.local.example`.
- [ ] 7.4 Verify: `uv run pytest --cov=bot --cov-report=term --cov-fail-under=70` + `npm run test`. Zero webhook references in `rg -l webhook bot/ dashboard/lib/`.

## Phase 8: Final verification

- [ ] 8.1 Full suite: `uv run pytest --cov-fail-under=70` + `npm run test`. Both green.
- [ ] 8.2 Coverage gate: bot coverage ≥70%.
- [ ] 8.3 Grep audit: `rg -r "webhook|WEBHOOK|TUNNEL_TOKEN" bot/ dashboard/lib/` returns empty.
- [ ] 8.4 Commit hygiene: each phase is one conventional commit with tests co-located.
