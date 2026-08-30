# Delta for Cache Layer

## ADDED Requirements

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
