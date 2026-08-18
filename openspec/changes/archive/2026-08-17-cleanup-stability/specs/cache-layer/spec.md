# Delta for cache-layer

## MODIFIED Requirements

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
