# Config Coverage Specification

## Purpose

Raise test coverage of `bot/core/config.py` from 0% to at least 80% through targeted unit tests, ensuring all configuration loading, validation, and default-fallback paths are exercised.

## Requirements

### Requirement: Config module reaches 80% coverage

Unit tests for `bot/core/config.py` MUST achieve at least 80% line coverage by the end of PR2. All public methods and configuration loading paths MUST be covered.

#### Scenario: Default config values applied

- GIVEN a guild with no custom configuration
- WHEN the config is loaded
- THEN default values are returned for all configuration fields

#### Scenario: Custom config values override defaults

- GIVEN a guild with custom configuration entries in the database
- WHEN the config is loaded
- THEN custom values are returned instead of defaults

#### Scenario: Invalid config falls back to defaults

- GIVEN a guild with malformed or missing configuration fields
- WHEN the config is loaded
- THEN invalid fields fall back to defaults without raising an exception

### Requirement: Coverage gate tracks config module

The project-wide coverage gate MUST include `bot/core/config.py` in its measurement. The gate value (55% after PR1, 60% after PR2, 70% after PR3) applies to the aggregate `bot/` coverage.

#### Scenario: Config coverage contributes to gate

- GIVEN config tests are added in PR2 raising `bot/core/config.py` to 80%
- WHEN the coverage gate is evaluated at 60%
- THEN the improved config coverage helps meet the gate
