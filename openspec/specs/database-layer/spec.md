# Database Layer Specification

## Purpose

Define the async database client and health-check behavior.

## Requirements

### Requirement: Async client

The system MUST provide an async Supabase client for database operations. `Database.__init__` MUST use `acreate_client` (async) instead of `create_client` (sync). ALL `.execute()` calls MUST be preceded by `await`. Database methods MUST return awaited results, not coroutines.

(Previously: used sync create_client; .execute() was not awaited)

#### Scenario: Query execution

- GIVEN the client is initialized
- WHEN a service executes a SELECT query
- THEN the client returns the matching rows

#### Scenario: Concurrent queries

- GIVEN multiple services query the database at the same time
- WHEN requests overlap
- THEN each request completes without blocking the others

#### Scenario: Async client creation

- GIVEN valid Supabase credentials
- WHEN `Database.connect()` is called
- THEN `acreate_client` is used (not sync `create_client`)

#### Scenario: All execute calls awaited

- GIVEN the Database has ~50 methods with `.execute()` calls
- WHEN a grep audit runs for `.execute()`
- THEN every occurrence is preceded by `await`

#### Scenario: Missed await detection

- GIVEN a method calls `.execute()` without `await`
- WHEN the method is called at runtime
- THEN a coroutine object is returned (not a response), causing `_unwrap()` to return `[]` — detectable by mypy or tests

### Requirement: Health check

The system MUST verify database connectivity on startup and report failure clearly.

#### Scenario: Healthy database

- GIVEN valid Supabase credentials
- WHEN the health check runs
- THEN it reports the database as reachable

#### Scenario: Unhealthy database

- GIVEN invalid or unreachable credentials
- WHEN the health check runs
- THEN it reports failure and the bot refuses to execute database-dependent commands

### Requirement: Database domain mixin split

The `Database` class MUST be split into domain mixins under `bot/core/db/`: `GuildDBMixin`, `MemberDBMixin`, `InfractionDBMixin`, `TicketDBMixin`, `TicketNoteDBMixin`, `TicketCategoryDBMixin`, `TicketAuditDBMixin`, `EconomyDBMixin`, `GreetingDBMixin`.

#### Scenario: All methods accessible

- GIVEN the Database class composes all mixins
- WHEN `db.get_guild()` or `db.insert_ticket()` is called
- THEN the method resolves from the correct mixin

#### Scenario: Mixin files exist

- GIVEN the split is complete
- WHEN inspecting `bot/core/db/`
- THEN each domain has its own file (e.g., `guild_db.py`, `ticket_db.py`)

### Requirement: Facade backward-compatible re-export

`bot/core/database.py` MUST re-export `Database` and all public names so existing imports `from bot.core.database import Database` continue to work unchanged.

#### Scenario: Existing import preserved

- GIVEN code imports `from bot.core.database import Database`
- WHEN the DB split is complete
- THEN the import resolves without error

#### Scenario: database.py is slim facade

- GIVEN the split is complete
- WHEN inspecting `bot/core/database.py`
- THEN it contains only imports and the composed `Database` class (~30 lines)
