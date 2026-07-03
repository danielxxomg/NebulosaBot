# Proposal: Webhook Cache Sync

## Intent

Close the ~5-minute cache desync window between dashboard writes (Vercel → Supabase) and the bot's RAM cache. Currently, when the dashboard mutates guild/economy/greeting config, the bot's TTLCache holds stale data until natural TTL expiry. The original design diagram (`Diagramas/DiagramaSecuencia.mmd:28-31`) specifies a `POST /webhook/sync` endpoint — it was never implemented.

## Scope

### In Scope
- `POST /webhook/sync` endpoint on the bot (aiohttp web.Application, in-process)
- HMAC-SHA256 signature verification (`WEBHOOK_SECRET` env var, shared secret)
- Payload: `{guild_id, entity}` → calls `invalidate_guild(guild_id)` (full guild invalidation)
- Fire-and-forget `fetch()` from 3 dashboard Server Actions after Supabase write
- New env vars: `WEBHOOK_SECRET`, `WEBHOOK_PORT` (bot); `BOT_WEBHOOK_URL`, `WEBHOOK_SECRET` (dashboard)
- Unit + integration tests (`aiohttp.test_utils.TestClient`)

### Out of Scope
- Per-entity targeted invalidation (deferred)
- Retry/backoff or dead-letter queue
- `GET /health` endpoint
- Metrics/observability
- Supabase Edge Function intermediary
- Rate limiting

## Capabilities

### New Capabilities
- `cache-sync-webhook`: POST /webhook/sync endpoint, HMAC-SHA256 verify, payload validation, `invalidate_guild()` call, aiohttp server lifecycle

### Modified Capabilities
- `guild-config`: dashboard `updateGuildConfig()` now fires webhook after Supabase write
- `economy-service`: dashboard `updateEconomyConfig()` now fires webhook after Supabase write
- `greeting-config`: dashboard `updateGreetingConfig()` now fires webhook after Supabase write

> Note: `economy_config` reads are NOT cached (direct DB per `gain_xp()`/`claim_daily()`), so the webhook is a safety net for future caching. Still included for consistency.

## Approach

In-process `aiohttp.web.Application` sharing the bot's event loop (zero new deps — `aiohttp` v3.14.1 is transitive via `discord.py`). Webhook module (`bot/webhook/`) started in `__main__.py` after bot connects. Dashboard signs requests with HMAC-SHA256; bot verifies with constant-time comparison before calling `invalidate_guild()`.

**Open design question**: TLS/exposure method for the bot port (Pterodactyl maps container→host port). Options: Cloudflare Tunnel (recommended — clean HTTPS, no port exposure), reverse proxy + Let's Encrypt, or HTTP+HMAC only. **Resolved in design phase**, not here.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `bot/webhook/server.py` | New | aiohttp app with `POST /webhook/sync` |
| `bot/webhook/auth.py` | New | HMAC-SHA256 verify middleware |
| `bot/webhook/models.py` | New | Request dataclass (guild_id, entity) |
| `bot/config.py` | Modified | Add `webhook_secret`, `webhook_port` fields |
| `bot/__main__.py` | Modified | Start webhook server alongside bot |
| `dashboard/lib/actions/guild-actions.ts` | Modified | Fire-and-forget webhook call |
| `dashboard/lib/actions/economy-actions.ts` | Modified | Fire-and-forget webhook call |
| `dashboard/lib/actions/greeting-actions.ts` | Modified | Fire-and-forget webhook call |
| `dashboard/.env.local.example` | Modified | Add `BOT_WEBHOOK_URL`, `WEBHOOK_SECRET` |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Port conflict (`WEBHOOK_PORT` in use) | Med | Catch `OSError`, log error, bot continues in degraded mode (stale cache until TTL) |
| Public bot port exposure (HTTP cleartext) | High | Flag as open design question; Cloudflare Tunnel recommended in design phase |
| Secret rotation requires coordinated restart | Low | Document procedure; future: support multiple secrets |
| Webhook unreachable → stale cache | Med | Fire-and-forget design; Supabase is source of truth; max 5 min staleness |

## Rollback Plan

1. Remove webhook call lines from 3 dashboard Server Actions (3 one-line deletions)
2. Remove `bot/webhook/` module
3. Revert `bot/__main__.py` (remove server startup)
4. Revert `bot/config.py` (remove webhook fields)
5. Remove env vars from `.env` files

No database migrations. No schema changes. Fully reversible via `git revert`.

## Dependencies

- `aiohttp` — already installed as transitive dependency of `discord.py` (v3.14.1 verified). **No new runtime dep.**

## Success Criteria

- [ ] `POST /webhook/sync` with valid HMAC returns 200 and evicts guild cache
- [ ] Invalid/missing HMAC returns 401
- [ ] Dashboard Server Actions fire webhook after Supabase write (fire-and-forget)
- [ ] All tests pass: `uv run pytest` (strict TDD — tests first)
- [ ] Bot starts normally with webhook server on configurable port
