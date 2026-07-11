# Slash Locale Translator Specification

## Purpose

Provide a discord.py `Translator` subclass that localizes slash command descriptions and parameter descriptions based on the user's Discord client locale. Command names remain English; only metadata strings localize.

## Requirements

### Requirement: Translator class registration

The system MUST provide a `Translator` subclass registered via `bot.tree.set_translator()` in `setup_hook`, before `tree.sync()`.

#### Scenario: Translator registered before sync

- GIVEN the bot starts
- WHEN `setup_hook` executes
- THEN `set_translator()` is called before `tree.sync()` and the Translator is active

### Requirement: Slash description localization

The Translator MUST resolve `locale_str` keys for command descriptions from locale files (`es.json`, `en.json`). The default message string (no locale match) MUST be Spanish. English MUST be provided via `description_localizations`.

#### Scenario: Spanish client sees Spanish description

- GIVEN a user with Discord client locale `es`
- WHEN they view `/ping` in the command picker
- THEN the description is shown in Spanish from `es.json`

#### Scenario: English client sees English description

- GIVEN a user with Discord client locale `en`
- WHEN they view `/ping` in the command picker
- THEN the description is shown in English from `en.json`

#### Scenario: Unknown locale falls back to Spanish

- GIVEN a user with Discord client locale `fr` (unsupported)
- WHEN they view `/ping`
- THEN the description falls back to the default Spanish string

### Requirement: Parameter description localization

The Translator MUST resolve `@app_commands.describe(...)` parameter descriptions from locale files.

#### Scenario: Parameter description in English

- GIVEN a user with client locale `en`
- WHEN they view `/ban` parameters
- THEN parameter descriptions (e.g., "reason") are shown in English

#### Scenario: Parameter description in Spanish

- GIVEN a user with client locale `es`
- WHEN they view `/ban` parameters
- THEN parameter descriptions are shown in Spanish

### Requirement: Command names stay English

Command names MUST NOT be localized. The Translator SHALL NOT provide `name_localizations` that change the command invocation string.

#### Scenario: Command name unchanged across locales

- GIVEN any supported client locale
- WHEN a user views the command picker
- THEN the command name is always the English string (e.g., `/ping`, `/ban`)

### Requirement: Locale keys in locale files

All slash description and parameter description keys MUST exist in both `es.json` and `en.json` under `slash.descriptions` and `slash.describes` namespaces.

#### Scenario: All 49 descriptions have keys

- GIVEN `es.json` and `en.json`
- WHEN all hybrid command descriptions are looked up
- THEN every description has a corresponding key in both locales

#### Scenario: All 30 parameter describes have keys

- GIVEN `es.json` and `en.json`
- WHEN all `@app_commands.describe(...)` parameters are looked up
- THEN every parameter description has a key in both locales

### Requirement: Post-registration hook for hybrid commands

The system MUST inject `description_localizations` into hybrid commands after registration, since `@commands.hybrid_command(description=...)` accepts `str`, not `locale_str`.

#### Scenario: Hybrid command gets localizations injected

- GIVEN a hybrid command registered with `description="Spanish default"`
- WHEN the post-registration hook runs
- THEN the command's `description_localizations` dict is populated with the English translation

### Requirement: Translator performance

The Translator MUST NOT make database calls. Locale data MUST be read from the in-memory locale dictionary loaded at startup.

#### Scenario: No DB round-trip during sync

- GIVEN locale data is loaded in memory
- WHEN `tree.sync()` triggers translation for all commands
- THEN zero database queries are executed
