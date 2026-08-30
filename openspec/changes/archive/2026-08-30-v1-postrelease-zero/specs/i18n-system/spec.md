# Delta for i18n-system

## MODIFIED Requirements

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
