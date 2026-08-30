# Operational Config Specification

## Purpose

Define the typed `config.toml` operational loader (restart-only) and bounded rotating file logging. Guild configuration and secrets stay in their existing homes (.env / database) — this spec governs process-level operational settings only.

## Requirements

### Requirement: Typed TOML loader with restart-only semantics

The system MUST load operational settings from `config.toml` via `tomllib` (stdlib 3.11, no new dependencies) into a typed structure covering: logging, limits, timeouts, retention defaults, and feature flags. Values are read at boot only — restart-only: runtime MUST NOT be required to re-read the file. When `config.toml` is ABSENT, the system MUST fall back to current environment-variable-only behavior and boot without error. Secrets (Discord token, DB credentials) and guild configuration MUST NOT move into `config.toml`; they remain sourced from `.env`/DB.

#### Scenario: Valid file applies typed values

- GIVEN a valid `config.toml` setting limits and timeouts
- WHEN the bot boots
- THEN the typed config object exposes those values and they govern behavior for the process lifetime

#### Scenario: Absent file falls back to env-only boot

- GIVEN no `config.toml` exists
- WHEN the bot boots
- THEN startup proceeds using environment variables/current defaults with no exception

#### Scenario: Malformed file fails fast at boot

- GIVEN a syntactically invalid `config.toml`
- WHEN the bot boots
- THEN a clear startup error identifies the parse failure (no silent partial config)

#### Scenario: Secrets stay out of TOML

- GIVEN the repository's `config.toml`
- WHEN its keys are inspected
- THEN no Discord token or DB credential keys exist; those values resolve from `.env`/DB as before

### Requirement: RotatingFileHandler bounds disk usage

File logging MUST use a `RotatingFileHandler` with maxBytes = 10 MB and backupCount = 5, bounding total log disk usage to approximately 60 MB (5 rotated files + active file). Rollover MUST prune the oldest backup beyond the fifth.

#### Scenario: Rollover at size threshold

- GIVEN the active log file reaches 10 MB
- WHEN the next record is written
- THEN the file rotates to a timestamped/indexed backup and logging continues unbounded in time

#### Scenario: Backup count capped at five

- GIVEN five backups already exist and another rollover occurs
- WHEN rotation completes
- THEN the oldest backup is deleted so at most 5 backups plus the active file remain

### Requirement: Token never logged at any level

The Discord token (and any fragment of it) MUST NOT appear in log output at ANY level. The startup INFO line that currently logs a token fragment (`bot/config.py`) MUST be removed or fully redacted. This holds regardless of log level or destination (console, rotating file).

#### Scenario: Boot logs contain no token material

- GIVEN the bot boots with a configured token
- WHEN all emitted log records are captured
- THEN no record at INFO (or any other level) contains any substring of the token

#### Scenario: Redaction survives level changes

- GIVEN log level is set to DEBUG
- WHEN startup completes
- STILL no token fragment appears in any captured record
