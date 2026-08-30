# Cache Layer Specification

## Purpose

Define the per-guild RAM cache with TTL expiry.

## Requirements

### Requirement: Per-guild TTL cache

The system MUST maintain a separate TTL cache entry for each guild with a default TTL of 300 seconds. Cache documentation MUST state the guild/configuration TTL, the accepted 30-second leaderboard window, and that member/economy Realtime invalidation is deferred to S2 rather than promised by this change.

#### Scenario: Guild cache isolation

- GIVEN guild A and guild B have different configurations
- WHEN the cache stores both
- THEN retrieving guild A returns guild A's configuration, not guild B's

#### Scenario: TTL expiry

- GIVEN a cached guild configuration
- WHEN 300 seconds pass without access
- THEN the entry expires and the next read fetches from the database

#### Scenario: TTL contract is documented

- GIVEN the cache documentation is inspected
- WHEN TTL values are read
- THEN guild/configuration TTL is 300 seconds and the leaderboard window is 30 seconds

#### Scenario: Leaderboard staleness is accepted

- GIVEN a leaderboard value is cached
- WHEN it is read within the 30-second window
- THEN the cache MAY serve the value without an immediate cross-instance refresh

#### Scenario: Member and economy Realtime work is deferred

- GIVEN member coins or economy configuration changes
- WHEN S1 cache guarantees are evaluated
- THEN no immediate Realtime invalidation guarantee is required and the S2 deferral is explicit

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

### Requirement: Eviction on guild remove

When the bot is removed from (or leaves) a guild G, the system MUST evict ALL cache entries scoped to G — every key matching `{G}:*` built via `cache_key(guild_id, entity)`. Eviction MUST occur on the leave/remove event and MUST NOT touch other guilds' entries. After eviction, a read for G MUST miss (no stale guild data retained in RAM).

#### Scenario: All guild keys evicted on remove

- GIVEN guild G has config, greeting, and ticket-cache entries
- WHEN the bot is removed from G
- THEN every `{G}:*` entry is gone from the cache in one eviction pass

#### Scenario: Other guilds unaffected

- GIVEN guilds A and B are both cached
- WHEN the bot is removed from A only
- THEN guild B's entries remain valid and readable

#### Scenario: Post-eviction read misses

- GIVEN guild G's entries were evicted after removal
- WHEN any code path reads a G-scoped key
- THEN the cache reports a miss (DB fallback executes; no stale value is served)

### Requirement: Documentation matches CDC invalidation reality

Cache-layer documentation (module docstrings/spec text) MUST claim ONLY invalidation paths that are actually implemented. The documented set of Realtime-invalidation streams MUST equal the set of registered CDC handlers. Until member/economy realtime invalidation ships, docs MUST continue to state it as deferred — never promised. A test MUST compare documented claims against registered handlers and fail on drift.

#### Scenario: Documented streams equal registered handlers

- GIVEN the documentation enumerates realtime-invalidation streams
- WHEN the parity test runs
- THEN each documented stream maps to a registered CDC handler and no handler is undocumented

#### Scenario: Deferred paths stay labeled deferred

- GIVEN member/economy realtime invalidation is not implemented
- WHEN docs/tests are evaluated
- THEN those paths appear as explicitly deferred, not as active guarantees

#### Scenario: Doc drift fails the suite

- GIVEN someone adds a CDC handler without updating documentation (or vice versa)
- WHEN the parity test runs
- THEN the test fails, forcing doc/reality sync before merge
