# Database Coverage Specification

## Purpose

Raise test coverage of `bot/core/database.py` from approximately 16% to at least 45% through targeted unit tests, ensuring critical database operations (CRUD, guild scoping, error handling) are exercised.

## Requirements

### Requirement: Database module reaches 45% coverage

Unit tests for `bot/core/database.py` MUST achieve at least 45% line coverage by the end of PR2. Priority paths include guild-scoped queries, CRUD operations, and error handling for missing records.

#### Scenario: Insert and retrieve a record

- GIVEN a valid dataclass model instance
- WHEN the record is inserted via the database layer
- THEN the record can be retrieved with matching fields

#### Scenario: Guild-scoped query filters correctly

- GIVEN records exist for multiple guilds
- WHEN a query filters by `guild_id`
- THEN only records for the target guild are returned

#### Scenario: Missing record returns None or empty

- GIVEN no record exists for a given primary key
- WHEN the database layer queries for it
- THEN the result is `None` or an empty list without raising an exception

#### Scenario: Upsert is idempotent

- GIVEN a record already exists
- WHEN the same record is upserted with identical data
- THEN no duplicate is created and the existing record is updated

### Requirement: Coverage gate tracks database module

The project-wide coverage gate MUST include `bot/core/database.py` in its measurement. The gate value applies to aggregate `bot/` coverage.

#### Scenario: Database coverage contributes to gate

- GIVEN database tests are added in PR2 raising `bot/core/database.py` to 45%
- WHEN the coverage gate is evaluated at 60%
- THEN the improved database coverage helps meet the gate
