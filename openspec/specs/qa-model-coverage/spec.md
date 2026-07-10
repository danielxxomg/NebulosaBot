# QA Model Coverage Specification

## Purpose

Unit tests proving dataclass round-trip correctness for `economy_config` and `member` models — both currently at 0% coverage.

## Requirements

### Requirement: EconomyConfig round-trip

Tests MUST prove `from_db_row` constructs valid instances and `to_db_dict` serializes back without data loss.

#### Scenario: from_db_row with all fields

- GIVEN a dict matching Supabase column names for economy_config
- WHEN `EconomyConfig.from_db_row(row)` is called
- THEN the returned instance has all fields populated from the row

#### Scenario: to_db_dict round-trip

- GIVEN an EconomyConfig instance constructed from a DB row
- WHEN `to_db_dict()` is called
- THEN the output dict keys and values match the original row

#### Scenario: Default values for missing keys

- GIVEN a row dict with missing optional keys
- WHEN `EconomyConfig.from_db_row(row)` is called
- THEN missing fields use documented defaults

### Requirement: Member round-trip with datetime

Tests MUST prove `from_db_row` parses datetime strings and `to_db_dict` serializes them to ISO format.

#### Scenario: from_db_row parses datetime fields

- GIVEN a row dict with ISO-format datetime strings
- WHEN `Member.from_db_row(row)` is called
- THEN datetime fields are `datetime` instances, not strings

#### Scenario: to_db_dict serializes datetime to ISO

- GIVEN a Member instance with datetime fields
- WHEN `to_db_dict()` is called
- THEN datetime values are ISO-format strings

#### Scenario: Defaults for missing optional fields

- GIVEN a row dict with missing optional fields
- WHEN `Member.from_db_row(row)` is called
- THEN optional fields use documented defaults without raising
