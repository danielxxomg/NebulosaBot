# Tasks: Localized, Branded Welcome and Goodbye UX

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | ~800 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | PR | Test cmd | Harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Migration, model, DB | PR 1 | `uv run pytest tests/test_greeting_config.py tests/test_greeting_db.py -v` | N/A — pure unit tests | `migrations/016_greeting_onboarding_channel.sql`, `bot/models/greeting_config.py`, `bot/core/db/greeting_db.py`, `tests/test_greeting_config.py`, `tests/test_greeting_db.py` |
| 2 | Locales, services | PR 2 (base=PR 1) | `uv run pytest tests/test_i18n.py tests/test_greeting_service.py tests/test_guild_service.py -v` | N/A — mocked Discord | `bot/locales/*.json`, `bot/services/greeting_service.py`, `bot/services/guild_service.py` |
| 3 | Renderer, cog, dashboard | PR 3 (base=PR 2) | `uv run pytest tests/test_image_service.py tests/test_greetings_cog.py tests/test_realtime.py -v` | N/A — mocked Discord | `bot/services/image_service.py`, `bot/cogs/greetings.py`, `dashboard/**` |

## Phase 1: Migration and Model

- [x] 1.1 RED: `tests/test_greeting_config.py` — null `onboardingChannelId` yields `None`; `to_db_dict()` round-trips non-null camelCase
- [x] 1.2 GREEN: `bot/models/greeting_config.py` — add `onboarding_channel_id: str | None = None`; update serialization
- [x] 1.3 RED: `tests/test_greeting_db.py` — `save_config()` upserts and `get_config()` returns field; clearing to null persists
- [x] 1.4 GREEN: `bot/core/db/greeting_db.py` — include `onboarding_channel_id` in CRUD payload
- [x] 1.5 Create `migrations/016_greeting_onboarding_channel.sql` — `ADD COLUMN IF NOT EXISTS "onboardingChannelId" TEXT`

## Phase 2: Locales and Services

- [x] 2.1 RED: `tests/test_i18n.py` — parametrize ES/EN: `t()` returns `greetings.card.*`/`greetings.cta.*`; `{count}`→`7`, `{channel}`→`<#123>`, no unresolved tokens
- [x] 2.2 RED: `tests/test_i18n.py` — remove EN key, assert ES fallback before raw key; `{count}`/`{channel}` don't collide with `{mention}`/`{user}`/`{server}`
- [x] 2.3 GREEN: `bot/locales/en.json`, `bot/locales/es.json` — add `greetings.card.{welcome_title,goodbye_title,member_count}`, `greetings.cta.welcome_onboarding`
- [x] 2.4 RED: `tests/test_greeting_service.py` — cache-first CRUD for `onboarding_channel_id`; CTA when channel resolvable; omitted when null/unresolvable; goodbye no CTA; custom msg + CTA present
- [x] 2.5 GREEN: `bot/services/greeting_service.py` — own CRUD, resolve `t()`, compose CTA, pass translated strings to renderer via `to_thread()`
- [x] 2.6 RED: `tests/test_guild_service.py` — `GuildService` delegates `onboarding_channel_id` to `GreetingService`
- [x] 2.7 GREEN: `bot/services/guild_service.py` — delegate greeting config to `GreetingService`; no duplicate field

## Phase 3: Renderer, Cog, Dashboard

- [x] 3.1 RED: `tests/test_image_service.py` — `generate_greeting_card()` uses supplied strings/icon; null icon and avatar failure use fallbacks
- [x] 3.2 GREEN: `bot/services/image_service.py` — updated signature; branded hierarchy; deterministic fallbacks
- [x] 3.3 RED: `tests/test_greetings_cog.py` — test commands render localized strings for ES guild; config shows onboarding status
- [x] 3.4 GREEN: `bot/cogs/greetings.py` — resolve translations, pass localized inputs, expose onboarding in config
- [x] 3.5 RED: `tests/test_realtime.py` — CDC with `onboardingChannelId` invalidates cache
- [x] 3.6 GREEN: ensure Realtime handler invalidates on `greeting_config` changes
- [x] 3.7 RED: `dashboard/__tests__/lib/actions/greeting-actions.test.ts` — parse/upsert `onboardingChannelId`; no webhook
- [x] 3.8 GREEN: `dashboard/lib/types.ts`, `dashboard/lib/actions/greeting-actions.ts`, `dashboard/.../greeting/page.tsx` — model, persist, expose onboarding channel
- [x] 3.9 Final: `uv run pytest -v` — all green, no regressions
