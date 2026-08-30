# Slash Locale Translator Specification

## Purpose

Provide a discord.py `Translator` subclass that localizes slash command descriptions and parameter descriptions based on the user's Discord client locale. Command names remain English; only metadata strings localize.

## Requirements

### Requirement: Translator class registration

The system MUST provide a `Translator` subclass registered via `bot.tree.set_translator()` in `setup_hook`, before `tree.sync()`, handling slash commands only. Prefix inert (`get_prefix=[]`).

#### Scenario: Translator registered before sync

- GIVEN the bot starts
- WHEN `setup_hook` executes
- THEN `set_translator()` is called before `tree.sync()` and the Translator is active for slash commands

### Requirement: Slash description localization

The Translator MUST resolve `locale_str` keys for slash command descriptions from locale files (`es.json`, `en.json`). The default message string (no locale match) MUST be Spanish via `t()` fallback. English MUST be provided via `description_localizations`.

(Previously: implicitly covered hybrid + slash; now slash-only)

#### Scenario: Spanish client sees Spanish description

- GIVEN a user with Discord client locale `es`
- WHEN they view `/ping` in the picker
- THEN description is Spanish from `es.json`

#### Scenario: English client sees English description

- GIVEN a user with client locale `en`
- WHEN they view `/ping` in the picker
- THEN description is English from `en.json`

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

Command names MUST NOT be localized. The Translator SHALL NOT provide `name_localizations` that change the command invocation string for slash commands.

#### Scenario: Command name unchanged across locales

- GIVEN any supported client locale
- WHEN a user views the picker
- THEN command name is always English (e.g., `/ping`, `/ban`)
### Requirement: Locale keys in locale files

All slash description and parameter description keys MUST exist in both `es.json` and `en.json` under `slash.descriptions` and `slash.describes` namespaces for slash commands.

(Previously: described as hybrid command descriptions)

#### Scenario: All 49 descriptions have keys

- GIVEN `es.json` and `en.json`
- WHEN all slash command descriptions are looked up
- THEN every description has a corresponding key in both locales

#### Scenario: All 30 parameter describes have keys

- GIVEN `es.json` and `en.json`
- WHEN all `@app_commands.describe(...)` parameters are looked up
- THEN every parameter description has a key in both locales

### Requirement: Post-registration hook for hybrid commands

The system MUST provide locale-aware descriptions for slash commands via `locale_str` / `description_localizations` on pure `@app_commands.command()` definitions. The legacy hybrid injection hook (`description_localizations` into `hybrid_command` after registration) is retired — no `hybrid_command` remains after S1 (only docstring examples at `bot/utils/checks.py:229,361`). For slash commands, `locale_str` keys are resolved by the Translator at `tree.sync()` time; Spanish is the default fallback.

(Previously: injected `description_localizations` into hybrid commands after registration since `@commands.hybrid_command(description=...)` accepts `str` not `locale_str`)

#### Scenario: Slash command localizations without hybrid injection

- GIVEN a slash command registered with `description=locale_str("slash.descriptions.ping")`
- WHEN `tree.sync()` runs with Translator active
- THEN Spanish default and English `description_localizations` are served per client locale without any hybrid post-hook

#### Scenario: No hybrid post-hook needed

- GIVEN the fully loaded command tree after S1
- WHEN decorators are inspected
- THEN zero `hybrid_command` decorators exist and no hybrid injection runs; only the two docstring literals at `checks.py:229,361` remain as substrings

### Requirement: Translator performance

The Translator MUST NOT make database calls. Locale data MUST be read from the in-memory locale dictionary loaded at startup.

#### Scenario: No DB round-trip during sync

- GIVEN locale data is loaded in memory
- WHEN `tree.sync()` triggers translation for all commands
- THEN zero database queries are executed
