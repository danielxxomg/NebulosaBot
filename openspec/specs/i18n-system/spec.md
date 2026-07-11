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

The system MUST provide locale keys under `slash.descriptions.*` and `slash.describes.*` namespaces in both `es.json` and `en.json` for all hybrid command descriptions and `@app_commands.describe(...)` parameter strings.

#### Scenario: Description keys exist for all commands

- GIVEN `es.json` and `en.json`
- WHEN `slash.descriptions.ping`, `slash.descriptions.ban`, etc. are looked up
- THEN non-empty strings are returned from both locales

#### Scenario: Describe keys exist for all parameters

- GIVEN `es.json` and `en.json`
- WHEN `slash.describes.ban_reason`, `slash.describes.ban_user`, etc. are looked up
- THEN non-empty strings are returned from both locales

#### Scenario: Spanish is default message string

- GIVEN the Translator resolves a key with no matching client locale
- WHEN the fallback fires
- THEN the Spanish (`es`) string is returned as the default message

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
