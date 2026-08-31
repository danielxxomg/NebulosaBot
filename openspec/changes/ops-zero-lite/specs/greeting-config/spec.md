# Delta for greeting-config

## ADDED Requirements

### Requirement: Greeting dispatch bound inherits greeting_config scope [PRESERVED]

The system MUST preserve that the per-guild Semaphore bound defined for `welcome-goodbye` applies to all code paths that resolve greeting config via `GreetingService.get_config` (`bot/services/greeting_service.py:63`) and dispatch via `dispatch_greeting`. `GreetingConfig` reads MUST stay cache-first (`cache_key(guild_id, "greeting_config")`, TTLCache) and Realtime CDC invalidated; no new cache MAY use bare entity keys — guild-scoped `cache_key(guild_id, entity)` from `bot.core.cache` is mandatory. `t(guild_id, key)` keys MUST exist in `bot/locales/{es,en}.json`.

#### Scenario: Cache-first path unchanged

- GIVEN greeting_config is cached for guild G
- WHEN `get_config(G)` is called during a burst
- THEN cache hit returns without DB query

#### Scenario: User-facing strings via t()

- GIVEN welcome/goodbye dispatch formats content/CTA
- WHEN strings are resolved
- THEN every literal comes from `t(guild_id, "<key>")` and keys exist in both locale files

#### Scenario: Guild-scoped cache key isolation

- GIVEN greeting avatar or config cache for guilds A and B
- WHEN reading for A
- THEN B's entry is not returned (`{guild_id}:entity` via `cache_key`)
