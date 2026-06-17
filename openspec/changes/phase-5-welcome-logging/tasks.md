# Tasks: Phase 5 — Welcome/Goodbye + Audit Logging

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~950 (additions + deletions) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 (feature-branch-chain) |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Data layer + LoggingService + GreetingService | PR 1 | Base: feature/tracker; migration, model, DB, services, tests |
| 2 | Welcome/Goodbye cards + GreetingsCog | PR 2 | Base: PR 1 branch; ImageService extension, cog, bot.py wiring |
| 3 | AuditListener + SentinelCog refactor | PR 3 | Base: PR 2 branch; 5 listeners, refactor 9 _log_action calls |

## Phase 1: Foundation — Data Layer & LoggingService

- [x] 1.1 Create `migrations/004_greeting_config.sql` with `greeting_config` table (PK guildId FK→guild, 8 columns per design)
- [x] 1.2 Create `bot/models/greeting_config.py` — `GreetingConfig` dataclass with `from_db_row()` / `to_db_dict()` (follow `EconomyConfig` pattern)
- [x] 1.3 Add `get_greeting_config()` and `upsert_greeting_config()` to `bot/core/database.py`
- [x] 1.4 Create `bot/services/logging_service.py` — `LoggingService` with 9 typed log methods, embed builders, `_can_log_in_channel()` visibility filter, config resolution via `GuildService`
- [x] 1.5 Create `bot/services/greeting_service.py` — `GreetingService` with `get_config()`, `save_config()`, `dispatch_welcome()`, `dispatch_goodbye()` (cache-first, delegates to `ImageService`)
- [x] 1.6 Create `tests/test_logging_service.py` — test embed building per event type, routing guards (disabled, missing channel, private channel skip)

## Phase 2: Welcome/Goodbye Feature

- [ ] 2.1 Add `generate_greeting_card()` to `bot/services/image_service.py` — reuse gradient, `_fetch_avatar()`, `_load_font()`; accept `card_type` param for welcome/goodbye styling
- [ ] 2.2 Create `bot/cogs/greetings.py` — `GreetingsCog` with `on_member_join`/`on_member_remove` listeners + `/welcome` `/goodbye` hybrid config commands (admin-gated)
- [ ] 2.3 Wire `GreetingService` + `GreetingsCog` in `bot/bot.py` — init service after `ImageService`, load extension
- [ ] 2.4 Add tests for `GreetingService.dispatch_welcome()` (enabled/disabled/missing channel) and `ImageService.generate_greeting_card()` (returns BytesIO PNG, avatar fallback)

## Phase 3: Audit Listener + SentinelCog Refactor

- [ ] 3.1 Create `bot/listeners/audit_listener.py` — `AuditListener` with 5 listeners: `on_message_edit`, `on_message_delete`, `on_member_update`, `on_guild_channel_create`, `on_guild_channel_delete` (early exits: bot, DM, log channel, disabled)
- [ ] 3.2 Refactor `bot/cogs/sentinel.py` — replace all 9 `_log_action()` calls with `self.bot.logging_service.log_moderation_action()`; delete `_log_action()` method
- [ ] 3.3 Wire `AuditListener` in `bot/bot.py` — load extension after `LoggingService` init
- [ ] 3.4 Add tests for `AuditListener` early exits (bot message, DM, own message, log channel, disabled logging, private channel) and verify SentinelCog handlers call `logging_service`
