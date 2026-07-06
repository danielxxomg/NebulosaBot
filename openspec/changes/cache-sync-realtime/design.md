# Design: Cache Sync Realtime

## Overview

Replace the inbound aiohttp webhook + Cloudflare Tunnel with an outbound Supabase Realtime subscriber. The bot keeps the existing sync `Database` client for data access and adds a separate async Realtime client, because Context7 confirms Python Realtime requires `acreate_client()`/`AsyncClient`; shutdown must manually remove channels with `remove_channel()`/`remove_all_channels()` because unused channels degrade Realtime performance. Supabase schema verification confirms `ticket.lastActivity` exists as `timestamp with time zone`, so it is safe for poll fallback increments.

```text
Dashboard write ─→ Supabase table ─→ Realtime CDC ─→ RealtimeCacheSubscriber
                                                        └─→ TTLCache.invalidate_guild()
WS unhealthy ────────────────────────────────────────────→ 30s poll fallback
```

## Architecture Decisions

| Area | Choice | Alternatives / Tradeoff | Rationale |
|---|---|---|---|
| Async client | Add async client only for Realtime | Migrating all DB calls is larger risk | Surgical change; preserves current sync query wrapper. |
| Channels | One channel `cache-sync` with four `on_postgres_changes(event="*", schema="public", table=...)` handlers | One channel per table increases cleanup surface | One lifecycle, lower overhead, still table-specific handlers. |
| Callbacks | Sync callback schedules `asyncio.create_task()` for async handler | Await inside callback may not be supported | Matches Context7 guidance for async methods from sync callbacks. |
| Health | 60s background task tracks latest `RealtimeSubscribeStates` | Trust SDK reconnect silently | Spec requires status logging and fallback after >60s unhealthy. |
| Poll | Brute-force config invalidation + ticket incremental query | Changed-row config impossible without `updated_at` | Small guild counts make full scan acceptable and correct. |
| Self-echo | In-memory TTL dict with lazy eviction | Background cleanup task is extra lifecycle | 5s TTL, no persistence, simple and deterministic. |

## Module Structure: `bot/core/realtime.py`

- `RecentWriteSet`: async-safe `dict[str, float]` guarded by `asyncio.Lock`; public `mark(table, identifier)` and `contains(table, identifier)` prune expired entries lazily. Key format is `{table}:{identifier}`. TTL defaults to 5s.
- `TicketGuildCache`: `ticket_id -> (guild_id, expires_at)` TTL mapping used by `ticket_note` handlers.
- `RealtimeCacheSubscriber`: constructor receives `supabase_url`, `supabase_key`, `TTLCache`, and optional async client factory. Public API: `start()`, `stop()`, `mark_recent_write(table, identifier)`. Internal tasks: `_health_loop`, `_poll_loop`, `_migration_watchdog`.

## Per-area Implementation Approach

Lifecycle: `start()` calls `acreate_client(url, key)`, creates `channel("cache-sync")`, registers `guild`, `greeting_config`, `ticket`, `ticket_note`, then awaits `channel.subscribe(on_subscribe)`. `on_subscribe(status, err)` stores status/time, logs success/errors, disables fallback on `SUBSCRIBED`. `stop()` cancels tasks, awaits `client.remove_channel(channel)`, then `client.remove_all_channels()` defensively; if the installed SDK exposes `aclose()`/`close()`, call it best-effort after channel cleanup.

CDC mapping: use `record` except DELETE uses `old_record` fallback. `guild` invalidates `record["id"]`; `greeting_config` invalidates `record["guildId"]`; `ticket` invalidates `record["guildId"]` and stores `ticket.id -> guildId`; `ticket_note` resolves `ticketId` through `TicketGuildCache`, then async Supabase query `ticket.select("guildId").eq("id", ticket_id).limit(1)`. If resolution fails, log warning and skip rather than invalidating the wrong guild.

Poll fallback: starts only after status is non-`SUBSCRIBED` for >60s; stops and resets `last_check` on recovery. Each 30s cycle records `window_end = now()` before queries and advances `last_check` only after success.

```sql
SELECT DISTINCT "guildId"::text AS guild_id
FROM public.ticket
WHERE "lastActivity" > $1 AND "lastActivity" <= $2;

SELECT id::text AS guild_id FROM public.guild
UNION
SELECT "guildId"::text AS guild_id FROM public.greeting_config;
```

The first query satisfies incremental ticket detection; the second deliberately brute-forces config-table invalidation and also covers ticket-note changes during WS outage. Application code may implement these through Supabase query builders or RPC, but tests should assert the intended filters/columns.

Migration: create an idempotent migration using `pg_publication_tables` checks before `ALTER PUBLICATION supabase_realtime ADD TABLE ...` for `guild`, `greeting_config`, `ticket`, `ticket_note`. Apply with Supabase MCP `apply_migration` before rollout. A 30s watchdog after first `SUBSCRIBED` logs: `No CDC events received — check that supabase_realtime publication includes the required tables`.

Wiring: `NebulosaBot.__slots__` replaces `_webhook_runner` with `_realtime_subscriber`; `setup_hook()` starts subscriber after cache/services are initialized and before final completion log; `close()` stops subscriber before `super().close()`. `app.py` becomes load dotenv, configure logging, import `bot.__main__.main`, `asyncio.run()` (<20 lines).

Dashboard/env cleanup: delete `dashboard/lib/webhook-sync.ts` and its test; remove imports/calls/mocks from `guild-actions`, `greeting-actions`, `economy-actions`. `ticket-actions.ts` already writes only Supabase and needs no webhook cleanup. Remove `WEBHOOK_SECRET`, `WEBHOOK_HOST`, `WEBHOOK_PORT`, `WEBHOOK_URL`, dashboard `WEBHOOK_SECRET`, and `TUNNEL_TOKEN`; remove webhook config fields/defaults.

## Test Strategy (TDD)

- RED tests first in `tests/test_realtime.py`: mock `acreate_client`, channel, `subscribe`, `remove_channel`, `remove_all_channels`.
- Handler tests: payloads with `record`, `old_record`, `type`, `table`, `schema`; assert `invalidate_guild()` calls and DELETE fallback.
- Self-echo tests: mark recent key, assert skip; advance monotonic beyond 5s, assert invalidation proceeds.
- Poll tests: fake async DB responses, assert ticket `lastActivity` window and full-scan guild invalidations.
- Health/watchdog tests: mock statuses, assert warning, fallback toggle, zero-CDC warning after 30s.
- Bot lifecycle tests: replace webhook wiring tests with subscriber start/stop ordering in `setup_hook()`/`close()`.
- Dashboard tests: remove webhook mocks and assert successful actions still revalidate paths.

## File-by-file Changes

| File | Action | Description |
|---|---|---|
| `bot/core/realtime.py` | Create | Subscriber, self-echo set, ticket guild resolver, health/poll tasks. |
| `bot/core/database.py` | Modify | Add optional recent-write tracker hooks to write methods where identifiers are known. |
| `bot/bot.py` | Modify | Replace webhook lifecycle with subscriber lifecycle. |
| `bot/webhook/*`, `tests/test_webhook_*.py` | Delete | Webhook capability removed. |
| `bot/config.py`, `.env.example`, `dashboard/.env.local.example` | Modify | Remove webhook/tunnel vars. |
| `app.py` | Modify | Remove cloudflared bootstrapping. |
| `dashboard/lib/webhook-sync.ts`, test | Delete | Realtime replaces dashboard callback. |
| `dashboard/lib/actions/*.ts` | Modify | Remove webhook imports/calls/mocks. |

## Risks

- High: publication migration not applied; mitigated by idempotent migration and watchdog warning.
- Medium: SDK close API not documented by Context7; mitigate with documented channel removal plus guarded best-effort close.
- Medium: poll fallback brute-force can churn cache on very large guild counts; acceptable for current scale.

## Open Questions Resolved

- Poll strategy: hybrid; ticket incremental plus full-scan guild/greeting invalidation.
- Self-echo: `{table}:{identifier}` TTL dict, lazy eviction, async lock.
- `ticket_note -> guildId`: cache first, then Supabase ticket lookup, skip on unresolved.
