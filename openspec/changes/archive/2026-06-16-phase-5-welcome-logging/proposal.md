# Proposal: Phase 5 — Welcome/Goodbye + Audit Logging

## Intent

Add configurable welcome/goodbye cards for member join/leave and centralized audit logging for 7 Discord event types. Logging is currently limited to moderation actions via `SentinelCog._log_action()` (private, duplicated). No greeting system exists.

## Scope

### In Scope
- Greeting columns on `guild` table (channels, message templates, card toggles)
- Welcome/goodbye card generation extending `ImageService` (reuse dark gradient, avatar, fonts)
- `GreetingsCog` — join/leave handlers + `/welcome` `/goodbye` config commands
- `LoggingService` — centralized log embed routing replacing `_log_action()`
- `AuditListener` — 7 listeners: message edit/delete, member join/leave/update, channel create/delete
- Channel filter: skip where `@everyone` has `read_messages=False`
- Content logging: before/after for edits, full content for deletes

### Out of Scope
- Voice state, role create/delete, nickname, emoji events (deferred)
- Custom card backgrounds, web dashboard config

## Capabilities

### New Capabilities
- `greeting-config`: GreetingConfig model + CRUD on guild table columns
- `welcome-goodbye`: Card generation via `ImageService.generate_greeting_card()`, join/leave handlers
- `audit-listener`: 7 event listeners with early-exit guards
- `logging-service`: Centralized `LoggingService` with typed event methods + embed routing

### Modified Capabilities
- `mod-logging`: Refactor `SentinelCog` to use `LoggingService` instead of `_log_action()`

## Approach

Greeting columns on guild table (1:1). Extend `ImageService` with `generate_greeting_card()` reusing gradient, `_fetch_avatar()`, `_load_font()`. Extract `_log_action()` into `LoggingService`. `AuditListener` follows `XPListener` pattern.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `bot/models/guild.py` | Modified | Add greeting columns |
| `bot/services/image_service.py` | Modified | Add `generate_greeting_card()` |
| `bot/services/logging_service.py` | New | Log routing + embeds |
| `bot/services/greeting_service.py` | New | Config CRUD + dispatch |
| `bot/cogs/greetings.py` | New | Join/leave + config cmds |
| `bot/listeners/audit_listener.py` | New | 7 audit listeners |
| `bot/cogs/sentinel.py` | Modified | Use LoggingService |
| `bot/core/database.py` | Modified | Greeting column I/O |
| `bot/bot.py` | Modified | Wire services + extensions |
| `migrations/004_greeting_columns.sql` | New | Guild table migration |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `on_message_edit` volume | Medium | Early-exit guards + cache-first |
| SentinelCog refactor breaks logging | Low | Test all 9 handlers |

## Rollback Plan

Revert migration 004, remove new extensions from `bot.py`, restore `_log_action()` from git. No data loss.

## Dependencies

- `Intents.message_content` and `Intents.members` enabled

## Success Criteria

- [ ] Welcome/goodbye cards send on join/leave when enabled
- [ ] All 7 audit events produce log embeds
- [ ] Channels invisible to `@everyone` excluded from logging
- [ ] Edits log before/after; deletes log full content
- [ ] SentinelCog mod logging unchanged via LoggingService
- [ ] Unit tests for all new code (pytest-asyncio)
