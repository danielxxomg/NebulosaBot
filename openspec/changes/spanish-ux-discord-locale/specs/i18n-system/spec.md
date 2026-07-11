# Delta for i18n-system

## ADDED Requirements

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
