# Design: Webhook Cache Sync

## Technical Approach

Add an in-process `aiohttp.web.Application` to `NebulosaBot` and start it on the existing Discord event loop. The endpoint `POST /webhook/sync` accepts signed dashboard notifications after Supabase writes and invalidates the bot RAM cache for the target guild. This follows the proposal scope: no database migrations, no retries, no metrics, no health endpoint, and no new runtime dependency; `aiohttp` is present in `uv.lock` as `3.14.1` via `discord-py`, while `requirements.txt` pins `aiohttp==3.9.5` as a transitive dependency.

## Architecture Decisions

| Decision | Options | Choice | Rationale |
|---|---|---|---|
| Webhook runtime | In-process aiohttp, separate worker, Supabase Edge Function | In-process `aiohttp.web.Application` | Shares the bot cache directly, uses existing `aiohttp`, and avoids cross-process coordination. Async server I/O does not block the Discord gateway. |
| Exposure / TLS | Cloudflare Tunnel, reverse proxy + Let's Encrypt, direct HTTP + HMAC | Cloudflare Tunnel | Dashboard is on Vercel and reaches Pterodactyl over the public internet. Tunnel provides HTTPS, hides the Pterodactyl port, and avoids host cert/proxy management. Reverse proxy is valid but operationally heavier. Direct HTTP+HMAC is functionally safe for `{guild_id, entity}` because HMAC gives auth/integrity and payload has no secrets, but it leaves metadata/body cleartext. |
| Auth | HMAC, mTLS, bearer token | HMAC-SHA256 | Simple shared-secret verification between Vercel and bot. mTLS is excessive for Pterodactyl + Vercel; bearer tokens lack request-body integrity. |
| Invalidation granularity | Per-entity, full guild | Full guild | Existing `TTLCache.invalidate_guild(guild_id)` removes every `{guild_id}:*` key and is idempotent; per-entity invalidation is out of scope. |

## Data Flow

```text
Bot startup -> setup_hook() initializes cache/services
            -> start AppRunner + TCPSite(WEBHOOK_HOST, WEBHOOK_PORT)

Dashboard Server Action
  -> write Supabase successfully
  -> body = { guild_id, entity }
  -> X-Webhook-Signature = HMAC_SHA256(body, WEBHOOK_SECRET).hexdigest()
  -> POST BOT_WEBHOOK_URL/webhook/sync (fire-and-forget)
  -> swallow/log POST failures

Bot webhook
  -> read raw body -> verify HMAC with compare_digest
  -> validate guild_id/entity -> cache.invalidate_guild(guild_id)
  -> 200 { ok: true }
```

## File Changes

| File | Action | Description |
|---|---|---|
| `bot/webhook/__init__.py` | Create | Package export for webhook server helpers. |
| `bot/webhook/auth.py` | Create | Signature calculation/verification using `X-Webhook-Signature`. |
| `bot/webhook/models.py` | Create | `WebhookSyncPayload` dataclass with `guild_id: str` and `entity: str`. |
| `bot/webhook/server.py` | Create | aiohttp app factory, route handler, runner/site lifecycle. |
| `bot/config.py` | Modify | Add `webhook_secret`, `webhook_host`, `webhook_port`; env vars: `WEBHOOK_SECRET`, `WEBHOOK_HOST` default `127.0.0.1`, `WEBHOOK_PORT` default `8080`. Pterodactyl uses `0.0.0.0`. |
| `bot/bot.py` | Modify | Start webhook in `setup_hook()` after cache init; store runner/site; cleanup during bot close/shutdown. |
| `dashboard/lib/webhook-sync.ts` | Create | Async helper signs and POSTs with `fetch`; catches/logs errors and never raises. |
| `dashboard/lib/actions/*-actions.ts` | Modify | Call helper after successful Supabase write and before/after `revalidatePath`; caller result unchanged. |
| `.env.example`, `dashboard/.env.local.example` | Modify | Document webhook URL/secret/host/port. |

## Interfaces / Contracts

- Endpoint: `POST /webhook/sync`
- Header: `X-Webhook-Signature: <hex hmac-sha256(raw_body, WEBHOOK_SECRET)>`
- Request JSON: `{ "guild_id": "123", "entity": "guild|economy|greeting" }`
- Responses: `200` valid and invalidated; `400` malformed payload; `401` missing/invalid signature; `503` if cache unavailable.
- Logging: use `logging.getLogger(__name__)`; never `print()`.

## Lifecycle / Failure Modes

Use `web.AppRunner(app)` and `web.TCPSite(runner, config.webhook_host, config.webhook_port)` started from `setup_hook()` after `self.cache = TTLCache()`. Catch `OSError` and unexpected startup errors, log with `exc_info=True`, and keep the Discord bot running in degraded TTL-only mode. Cleanup calls `runner.cleanup()` during bot shutdown. If webhook or bot is down, the dashboard write still succeeds and the POST failure is only logged.

## Deployment / TLS

Run `cloudflared` beside the Pterodactyl allocation or on the host, forwarding `https://bot-webhook.example.com` to `http://127.0.0.1:<WEBHOOK_PORT>` or the mapped local port. Configure Vercel `BOT_WEBHOOK_URL=https://bot-webhook.example.com` and the same `WEBHOOK_SECRET` as the bot. Pterodactyl binds `WEBHOOK_HOST=0.0.0.0`; Cloudflare controls public ingress, so the raw port does not need public exposure.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | HMAC valid/invalid/missing; payload dataclass validation | `pytest`, `pytest.mark.asyncio`, constant-time compare path. |
| Integration | `POST /webhook/sync` invalidates mocked/real `TTLCache`; repeat calls are no-op | aiohttp test client; run with `uv run pytest`. Add `pytest-aiohttp` only as a dev dependency if the current test utilities are insufficient. |
| Dashboard | Helper signs exact raw body and swallows fetch failures | Mock `fetch`/console logging in dashboard test setup; no caller exception. |

## Migration / Rollout

No database migration required. Roll out by setting env vars, starting bot with webhook enabled, then enabling dashboard calls. Rollback removes dashboard helper calls and webhook startup/module.

## Open Questions

None.
