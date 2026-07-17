# Design: Localized, Branded Welcome and Goodbye UX

## Technical Approach

Keep orchestration in `GreetingService`, caller-side translation, and existing Pillow rendering. `GreetingService` will resolve `t(guild_id, ...)` keys for ES/EN card copy and the welcome CTA, compose message content, resolve safe Discord assets, and invoke Pillow through `asyncio.to_thread()`. Dashboard writes nullable onboarding directly to Supabase; Realtime CDC refreshes bot cache entries.

**CRUD contract:** `GuildService` is the setup/admin facade: its cache-first path delegates greeting reads/updates, including `onboarding_channel_id`, to `GreetingService`, avoiding a duplicate field while publishing language. `GreetingService` owns `greeting_config`: `get_config()` checks greeting cache then DB; `save_config()` upserts the optional field and invalidates it. A `greeting_config` Realtime CDC event invalidates the guild greeting key, so the next read sees dashboard changes without a webhook.

## Architecture Decisions

| Option | Tradeoff | Decision |
|---|---|---|
| Translate inside Pillow | Couples rendering to guild state and makes tests harder | **Reject**; pass fully formatted `greeting_title` and `member_count_text` from callers. |
| Add CTA to the image | Strong visual prominence but mixes onboarding action with identity banner | **Reject**; keep the banner identity-focused and put the CTA in message content. |
| Add a separate onboarding table/service | More normalization, but unnecessary for one optional guild setting | **Reject**; add one nullable field to `greeting_config`, preserving the existing cache-first CRUD path. |
| Use Discord/API fetches during dispatch | Handles cache misses but adds latency and failure modes | **Reject**; resolve configured channels/assets from the guild cache and omit only inaccessible CTA/assets. |

The banner retains the current gradient foundation but gains a clear hierarchy: guild identity/accent treatment, circular guild icon treatment, member avatar/name, and member count. Missing assets render deterministic placeholders rather than aborting delivery.

## Data Flow

```text
GuildService language map ──→ t() ──→ GreetingService
Dashboard Server Action ──→ Supabase greeting_config ──→ Realtime invalidation
Member + Guild assets ──→ GreetingService ──→ to_thread(Pillow) ──→ Discord channel
                                      └── custom message + optional CTA
```

## File Changes

| File | Action | Description |
|---|---|---|
| `bot/models/greeting_config.py` | Modify | Add nullable `onboarding_channel_id`; preserve camelCase serialization/defaults. |
| `bot/core/db/greeting_db.py` | Modify | Continue generic row CRUD with the expanded model payload. |
| `bot/services/guild_service.py` | Modify | Keep setup/admin CRUD cache-first and delegate greeting configuration, including `onboarding_channel_id`, to `GreetingService`. |
| `bot/services/greeting_service.py` | Modify | Resolve translations/assets, own greeting CRUD, compose CTA with custom text, and keep goodbye CTA-free. |
| `bot/services/image_service.py` | Modify | Accept pretranslated strings and guild icon; render premium hierarchy and safe placeholders. |
| `bot/cogs/greetings.py` | Modify | Pass localized inputs/assets for live test cards and expose onboarding status in config output. |
| `bot/locales/en.json`, `bot/locales/es.json` | Modify | Add `greetings.card.*` and `greetings.cta.*` keys. |
| `migrations/016_greeting_onboarding_channel.sql` | Create | Add nullable `onboardingChannelId` with `ADD COLUMN IF NOT EXISTS`. |
| `dashboard/lib/types.ts`, `dashboard/app/(authenticated)/guilds/[guildId]/greeting/page.tsx` | Modify | Model and expose the optional onboarding channel. |
| `dashboard/lib/actions/greeting-actions.ts` | Modify | Parse, validate, and upsert the field without a webhook. |
| `tests/test_greeting_config.py`, `tests/test_greeting_db.py`, `tests/test_guild_service.py`, `tests/test_greeting_service.py`, `tests/test_image_service.py`, `tests/test_greetings_cog.py`, `tests/test_i18n.py`, `tests/test_realtime.py`, `dashboard/__tests__/lib/actions/greeting-actions.test.ts` | Modify | Strict-TDD coverage for contracts, service CRUD/cache ownership, concrete i18n interpolation and fallback scenarios, CTA behavior, migration payloads, and CDC invalidation. |

## Interfaces / Contracts

```python
GreetingConfig.onboarding_channel_id: str | None
ImageService.generate_greeting_card(
    *, username: str, guild_name: str, member_count: int,
    avatar_url: str | None, guild_icon_url: str | None,
    greeting_title: str, member_count_text: str, card_type: str,
) -> io.BytesIO
```

`greeting_title` and `member_count_text` are fully translated/formatted before rendering. CTA composition uses `<#channel_id>` only after `guild.get_channel()` resolves the configured channel; invalid or missing targets produce no CTA and do not prevent delivery.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | Model, `t()`, Pillow, asset fallbacks | Parametrize ES/EN; inspect renderer args/PNG and patch fetch failures. In `tests/test_i18n.py`, assert `{count}` → `7` and `{channel}` → `<#123>` with no unresolved tokens; assert `{mention}`, `{user}`, `{server}` stay in message-template formatting. Remove the English key in a fixture and assert Spanish fallback before the raw key. |
| Integration | Dispatch, cache, Realtime, Server Action | Mock Discord objects; assert custom message plus CTA, goodbye exclusion, cache-first reads, CDC invalidation, validation, and null round-trip. Prove `GuildService` delegates the field and `GreetingService` returns it after cache invalidation. |
| E2E | N/A | Repository config marks E2E unavailable; verify through focused integration tests. |

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary.

## Migration / Rollout

Apply the additive migration before deploying application/dashboard changes. Existing rows remain valid with `NULL`; the feature is immediately backward-compatible. Rollback removes the application/dashboard field and migration column only after disabling CTA writes.

## Open Questions

- [ ] None blocking. Exact accent colors and final copy remain implementation-level visual/copy tuning within the existing banner palette.
