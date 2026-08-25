# Delta for logging-service

> Change: `cycle-5-quality-zero`. Scope: log embed strings localized via `t(guild_id, ...)` per guild language; orphan `voice.*` locale keys wired; interpolation params supported.

## ADDED Requirements

### Requirement: Localized log embed strings

All user-facing strings in `LoggingService` embeds (titles, descriptions) MUST be resolved through `t(guild_id, "<key>")` using the target guild's configured language — hardcoded English literals MUST NOT remain in the service. The currently orphaned `voice.*` locale keys (`join_title`, `join_description`, `leave_title`, `leave_description`, `move_title`, `move_description`, `mute_title`, `mute_description`, `deafen_title`, `deafen_description`) MUST be wired into `log_voice_event`. Interpolation parameters (e.g. `{mention}`, `{channel}`, `{from}`, `{to}`, `{state}`) MUST be substituted into the localized templates. Every key referenced by the service MUST exist in both `bot/locales/es.json` and `bot/locales/en.json` (enforced by the i18n AST scanner and `tests/test_i18n_key_coverage.py`). Embed routing guards (skip when disabled or channel missing) are unchanged.

#### Scenario: Spanish guild voice join embed is localized

- GIVEN a guild whose language is Spanish
- WHEN `log_voice_event()` logs a voice join
- THEN the embed title/description come from the `es` `voice.join_*` keys

#### Scenario: English guild voice join embed is localized

- GIVEN a guild whose language is English
- WHEN `log_voice_event()` logs a voice join
- THEN the embed title/description come from the `en` `voice.join_*` keys (not the hardcoded fallback)

#### Scenario: Interpolation params are substituted

- GIVEN a voice move event with member and channels
- WHEN the localized description template is rendered
- THEN `{mention}`, `{from}`, and `{to}` are replaced with actual values (no raw placeholders in the embed)

#### Scenario: Locale coverage holds for all logging keys

- GIVEN every `t()` key referenced by `LoggingService`
- WHEN the i18n coverage test scans both locale files
- THEN each key exists in both `es.json` and `en.json`

#### Scenario: Routing guards unchanged

- GIVEN `logEnabled` is false or `logChannelId` is null
- WHEN any localized log method is called
- THEN no embed is sent (existing Embed routing behavior preserved)
