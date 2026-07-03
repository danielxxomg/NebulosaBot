# Tasks: Webhook Cache Sync

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~380–450 |
| 400-line budget risk | Medium |
| Chained PRs recommended | Yes |
| Suggested split | PR 1: bot webhook + tests (~230 lines) · PR 2: dashboard + env + deps (~150 lines) |
| Delivery strategy | ask-always |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Bot webhook module + tests | PR 1 | Self-contained; ~230 lines |
| 2 | Dashboard helper + actions + env + deps | PR 2 | Depends on PR 1; ~150 lines |

---

## Phase 1: Foundation — Config & Models

- [x] 1.1 **TDD — BotConfig webhook fields** (`bot/config.py`, `tests/test_config.py`)
  RED: tests for `from_env` loading `WEBHOOK_SECRET` (""), `WEBHOOK_HOST` ("127.0.0.1"), `WEBHOOK_PORT` (8080).
  GREEN: add fields + load in `from_env`. Absent secret → warning; absent port/host → defaults.

- [x] 1.2 **TDD — WebhookSyncPayload** (`bot/webhook/models.py`, `tests/test_webhook_models.py`)
  RED: tests for `WebhookSyncPayload(guild_id: int, entity: str)` + `from_json_bytes()` — valid, missing guild_id → ValueError, malformed → ValueError.
  GREEN: `bot/webhook/__init__.py` + dataclass + classmethod.

## Phase 2: Core — Auth & Server

- [x] 2.1 **TDD — HMAC verify** (`bot/webhook/auth.py`, `tests/test_webhook_auth.py`)
  RED: tests for `compute_signature`/`verify_signature` — valid, missing, tampered, empty secret.
  GREEN: `hmac.new` + `hmac.compare_digest`.

- [x] 2.2 **TDD — Webhook endpoint** (`bot/webhook/server.py`, `tests/test_webhook_server.py`)
  RED: `aiohttp.test_utils.TestClient` — valid→200+invalidate, missing sig→401, bad sig→401, malformed→400, no guild_id→400, duplicate→idempotent.
  GREEN: `create_webhook_app(cache, secret) -> Application` with `POST /webhook/sync`.

- [x] 2.3 **TDD — Server lifecycle** (`bot/webhook/server.py`, `tests/test_webhook_server.py`)
  RED: `start_webhook_server(host, port, cache, secret)` — valid→(runner,site), port conflict→None+log, no secret→None+log.
  GREEN: `AppRunner` + `TCPSite`, catch `OSError`.

## Phase 3: Bot Wiring

- [x] 3.1 **TDD — setup_hook integration** (`bot/bot.py`, `tests/test_bot.py`)
  RED: tests — calls `start_webhook_server` after cache; stores runner; `close()` cleans up; degraded→continues.
  GREEN: add slots; call startup in `setup_hook`; override `close()`.

## Phase 4: Dashboard

- [x] 4.1 **TDD — Webhook helper** (`dashboard/lib/webhook-sync.ts`, test)
  RED: vitest — signs body, POSTs, catches errors. Mock fetch+crypto.
  GREEN: `crypto.createHmac`, fire-and-forget `fetch().catch(console.error)`.
- [x] 4.2 **TDD — Wire guild-actions** (file + test) — `sendWebhookSync(gid, "guild_config")` after write.
- [x] 4.3 **TDD — Wire economy-actions** (file + test) — `sendWebhookSync(gid, "economy_config")`.
- [x] 4.4 **TDD — Wire greeting-actions** (file + test) — `sendWebhookSync(gid, "greeting_config")`.

## Phase 5: Env & Dependencies

- [x] 5.1 **Update .env.example** — add `WEBHOOK_SECRET`, `WEBHOOK_HOST`, `WEBHOOK_PORT`.
- [x] 5.2 **Update dashboard/.env.local.example** — add `BOT_WEBHOOK_URL`, `WEBHOOK_SECRET`.
- [x] 5.3 **Reconcile aiohttp** (`requirements.txt`) — pin 3.14.1 to match uv.lock. Verify tests pass.

## Phase 6: Verification

- [x] 6.1 **Full suite** — `uv run pytest` + `cd dashboard && npx vitest run`. Coverage ≥ 70%.
