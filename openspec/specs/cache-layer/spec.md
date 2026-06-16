# Cache Layer Specification

## Purpose

Define the per-guild RAM cache with TTL expiry.

## Requirements

### Requirement: Per-guild TTL cache

The system MUST maintain a separate TTL cache entry for each guild with a default TTL of 5 minutes.

#### Scenario: Guild cache isolation

- GIVEN guild A and guild B have different configurations
- WHEN the cache stores both
- THEN retrieving guild A returns guild A's configuration, not guild B's

#### Scenario: TTL expiry

- GIVEN a cached guild configuration
- WHEN 5 minutes pass without access
- THEN the entry expires and the next read fetches from the database

### Requirement: Cache operations

The system MUST support get, set, and invalidate operations for guild-scoped data.

#### Scenario: Cache hit

- GIVEN a guild configuration is in cache
- WHEN a read request arrives
- THEN the cached value is returned without querying the database

#### Scenario: Cache invalidation

- GIVEN a guild configuration is cached
- WHEN the configuration is updated
- THEN the cached entry is invalidated
