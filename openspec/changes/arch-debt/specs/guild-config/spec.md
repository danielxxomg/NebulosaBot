# Delta for Guild Configuration

## ADDED Requirements

### Requirement: Concurrent guild backfill on startup

`on_ready` guild backfill MUST use `asyncio.gather()` instead of sequential awaits. Backfill MUST handle concurrent guild config fetches without race conditions.

(Previously: sequential for-loop with await per guild)

#### Scenario: Multiple guilds backfilled concurrently

- GIVEN the bot is a member of 5 guilds at startup
- WHEN `on_ready` fires
- THEN all 5 `ensure_guild_exists` calls run concurrently via `asyncio.gather()`

#### Scenario: Large guild count bounded

- GIVEN the bot is a member of 100+ guilds
- WHEN `on_ready` fires
- THEN `asyncio.gather()` completes without overwhelming Supabase (rate limits apply at client level)
