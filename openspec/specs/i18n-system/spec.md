# i18n-system Specification

## Purpose

Provide a centralized internationalization system that resolves localized strings per guild, supporting Spanish and English with fallback behavior and placeholder interpolation.

## Requirements

### Requirement: Locale file loading

The system MUST load locale JSON files (`es.json`, `en.json`) from `bot/locales/` at startup into an in-memory dictionary keyed by locale code.

#### Scenario: Load supported locales

- GIVEN `es.json` and `en.json` exist in `bot/locales/`
- WHEN the bot starts
- THEN both locale dictionaries are available in memory

#### Scenario: Missing locale file

- GIVEN a locale file is missing from disk
- WHEN the bot starts
- THEN the system logs a warning and continues with available locales

### Requirement: Translation lookup function

The system MUST provide a synchronous `t(guild_id, key, **kwargs)` function that returns a localized string by resolving the guild's configured language.

#### Scenario: Lookup with valid key

- GIVEN guild 123 has language `en` configured
- WHEN `t(123, "commands.ping.response", latency=42)` is called
- THEN the English string for `commands.ping.response` is returned with `{latency}` replaced by `42`

#### Scenario: Lookup with missing key

- GIVEN guild 123 has language `en` configured
- WHEN `t(123, "nonexistent.key")` is called
- THEN the system falls back to the Spanish (`es`) locale for that key

#### Scenario: Fallback exhausted

- GIVEN the key does not exist in `en` or `es`
- WHEN `t(123, "missing.key")` is called
- THEN the raw key string `"missing.key"` is returned and a warning is logged

### Requirement: Dot-notation keys

Locale keys MUST use flat dot-notation (e.g., `commands.ping.response`) mapping to nested JSON paths.

#### Scenario: Resolve nested key

- GIVEN `en.json` contains `{ "commands": { "ping": { "response": "Pong! {latency}ms" } } }`
- WHEN `t(123, "commands.ping.response", latency=42)` is called
- THEN `"Pong! 42ms"` is returned

### Requirement: Fallback chain

The system MUST fall back to `es` (Spanish) when the guild's configured locale lacks a key, before returning the raw key.

#### Scenario: English key missing, Spanish exists

- GIVEN guild language is `en` and `commands.new.key` exists only in `es.json`
- WHEN `t(guild_id, "commands.new.key")` is called
- THEN the Spanish value is returned

### Requirement: Placeholder interpolation

Translation strings MAY contain `{placeholder}` tokens that MUST be replaced by matching `kwargs` passed to `t()`.

#### Scenario: All placeholders resolved

- GIVEN a string `"Welcome {user} to {channel}"`
- WHEN `t(guild_id, "welcome.msg", user="Alice", channel="#general")` is called
- THEN `"Welcome Alice to #general"` is returned

#### Scenario: Missing placeholder argument

- GIVEN a string `"Hello {user}"` and `kwargs` does not include `user`
- WHEN `t(guild_id, "greeting")` is called
- THEN the raw `{user}` token remains in the output and a warning is logged

### Requirement: Sync performance

The `t()` function MUST perform a synchronous dict lookup with no database call per invocation.

#### Scenario: No DB round-trip

- GIVEN locale data is loaded in memory
- WHEN `t()` is called 1000 times
- THEN zero database queries are executed

### Requirement: Slash metadata locale keys

The system MUST provide locale keys under `slash.descriptions.*` and `slash.describes.*` namespaces in both `es.json` and `en.json` for all slash command descriptions (`@app_commands.command(description=...)` via `locale_str`) and `@app_commands.describe(...)` parameter strings. No hybrid command metadata remains; the only surviving `hybrid_command` substrings are docstring examples at `bot/utils/checks.py:229,361`.

(Previously: for all hybrid command descriptions and `@app_commands.describe(...)` parameter strings)

#### Scenario: Description keys exist for all commands

- GIVEN `es.json` and `en.json`
- WHEN `slash.descriptions.ping`, `slash.descriptions.ban`, etc. are looked up via `t()` or Translator
- THEN non-empty strings are returned from both locales

#### Scenario: Describe keys exist for all parameters

- GIVEN `es.json` and `en.json`
- WHEN `slash.describes.ban_reason`, `slash.describes.ban_user`, etc. are looked up
- THEN non-empty strings are returned from both locales

#### Scenario: Spanish is default message string

- GIVEN the Translator resolves a key with no matching client locale
- WHEN the fallback fires
- THEN the Spanish (`es`) string is returned as the default message

#### Scenario: No hybrid metadata required

- GIVEN the command tree after S1
- WHEN slash metadata keys are audited
- THEN zero keys depend on `hybrid_command` registration; all are slash `locale_str` keys
### Requirement: Greeting card and CTA locale keys

The system MUST provide greeting card and welcome CTA locale keys in both `es.json` and `en.json` under the `greetings.card.*` and `greetings.cta.*` namespaces. Keys MUST include a welcome title, a goodbye title, a member-count string, and a welcome onboarding CTA string. Spanish and English values MUST be independently resolvable via `t()`.

#### Scenario: Spanish card keys resolvable

- GIVEN `es.json` contains `greetings.card.welcome_title`, `greetings.card.goodbye_title`, and `greetings.card.member_count`
- WHEN `t(guild_id, "greetings.card.welcome_title")` is called for a Spanish guild
- THEN a non-empty Spanish string is returned

#### Scenario: English card keys resolvable

- GIVEN `en.json` contains the `greetings.card.*` keys
- WHEN `t(guild_id, "greetings.card.member_count", count=42)` is called for an English guild
- THEN a non-empty English string with `42` interpolated is returned

#### Scenario: Member count placeholder interpolation

- GIVEN `greetings.card.member_count` contains a `{count}` placeholder
- WHEN `t(guild_id, "greetings.card.member_count", count=7)` is called
- THEN the returned string contains `7` and no unresolved `{...}` tokens

#### Scenario: Welcome CTA keys resolvable with channel placeholder

- GIVEN `greetings.cta.welcome_onboarding` contains a `{channel}` placeholder
- WHEN `t(guild_id, "greetings.cta.welcome_onboarding", channel="<#123>")` is called
- THEN the returned string contains the channel mention and no unresolved `{...}` tokens

#### Scenario: Distinct placeholder namespace

- GIVEN the `greetings` namespace uses `{count}` and `{channel}` placeholders
- WHEN greeting templates use `{mention}`, `{user}`, and `{server}`
- THEN the greeting-card placeholders (`{count}`, `{channel}`) do not collide with the message-template placeholders

#### Scenario: Fallback chain still applies to greeting keys

- GIVEN a guild configured with language `en` and `greetings.card.welcome_title` exists only in `es.json`
- WHEN `t(guild_id, "greetings.card.welcome_title")` is called
- THEN the system falls back to the Spanish value before returning the raw key

### Requirement: Edit category audit i18n keys

The system MUST provide `tickets.actions.edit_category_audit_title` and `tickets.actions.edit_category_audit_description` keys in both `en.json` and `es.json`. These keys MUST support `{old_category}`, `{new_category}`, and `{actor}` placeholder tokens.

#### Scenario: Audit keys present in both locales

- GIVEN `en.json` and `es.json` under `bot/locales/`
- WHEN `t(guild_id, "tickets.actions.edit_category_audit_title")` is called for each locale
- THEN a non-empty string is returned from both `en.json` and `es.json`

#### Scenario: Audit placeholders resolve correctly

- GIVEN `tickets.actions.edit_category_audit_description` contains `{old_category}`, `{new_category}`, `{actor}`
- WHEN `t(guild_id, "tickets.actions.edit_category_audit_description", old_category="Support", new_category="Billing", actor="<@123>")` is called
- THEN the returned string contains "Support", "Billing", and "<@123>" with no unresolved `{...}` tokens

<!-- BEGIN DELTA: cycle-4-debt-zero (i18n-system) -->
## ADDED Requirements

### Requirement: Translation key coverage test

An automated test MUST statically scan `bot/` sources for literal translation keys passed to `t()` and assert every such key exists in BOTH `es.json` and `en.json`. Dynamically composed keys MUST be exempted exclusively via a module-level `DYNAMIC_KEY_PATTERNS` allowlist of regex patterns (e.g. covering `tickets.timer.unit_*` and `ocio.8ball.r\d+`); each allowlist entry MUST correspond to a genuinely dynamic key family. A violation MUST fail with a single consolidated report listing every missing key together with its callsite `file:line`. Unused-key detection is advisory only (it MUST NOT fail the suite).

#### Scenario: Missing static key fails with callsite

- GIVEN a literal `t(guild, "some.missing.key")` call in `bot/` and the key absent from a locale file
- WHEN the coverage test runs
- THEN it fails listing `some.missing.key` with the originating file and line

#### Scenario: Dynamic keys do not false-fail

- GIVEN a runtime composition such as `f"tickets.timer.unit_{unit}"` matches a `DYNAMIC_KEY_PATTERNS` entry
- WHEN the scanner encounters the composition site
- THEN no failure is raised for that dynamic key family

#### Scenario: Both locales must agree

- GIVEN a literal key exists in `es.json` but not `en.json`
- WHEN the coverage test runs
- THEN it fails (both locales are required for every literal key)

### Requirement: Ticket timer locale keys

Both locale files MUST gain the `tickets.timer.*` namespace used by the scheduled-close flow — including its title/body strings and the `unit_second` through `unit_day` units interpolated via `{unit}` — so users never see raw keys. The locale files MUST gain ONLY these new keys plus the eight-ball title key below; existing keys, JSON structure, and translations MUST remain untouched.

#### Scenario: Timer keys resolve in both locales

- GIVEN `es.json` and `en.json`
- WHEN `t(guild, "tickets.timer.scheduled_title")` and the unit keys resolve
- THEN non-empty localized strings return from both locales with `{unit}` interpolating correctly

#### Scenario: Raw keys never reach users

- GIVEN the scheduled-close flow renders its embeds
- WHEN any timer string is resolved
- THEN no raw `tickets.timer.` key appears in user-visible output

### Requirement: Eight-ball embed title key

Both locale files MUST gain `ocio.8ball.embed_title`. The existing `ocio.8ball.r1`–`r20` responses and all other existing translations MUST remain byte-for-byte unchanged.

#### Scenario: Title resolves in both locales

- GIVEN `es.json` and `en.json`
- WHEN `t(guild, "ocio.8ball.embed_title")` is called
- THEN a non-empty localized title returns from both locales

#### Scenario: Existing translations untouched

- GIVEN the new keys are added to both locale files
- WHEN any pre-existing key is compared against its prior value
- THEN every pre-existing key and structure is unchanged
<!-- END DELTA: cycle-4-debt-zero (i18n-system) -->
