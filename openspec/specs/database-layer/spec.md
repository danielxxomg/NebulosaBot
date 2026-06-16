# Database Layer Specification

## Purpose

Define the async database client and health-check behavior.

## Requirements

### Requirement: Async client

The system MUST provide an async Supabase client for database operations.

#### Scenario: Query execution

- GIVEN the client is initialized
- WHEN a service executes a SELECT query
- THEN the client returns the matching rows

#### Scenario: Concurrent queries

- GIVEN multiple services query the database at the same time
- WHEN requests overlap
- THEN each request completes without blocking the others

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
