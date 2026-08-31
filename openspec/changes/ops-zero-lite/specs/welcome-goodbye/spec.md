# Delta for welcome-goodbye

## ADDED Requirements

### Requirement: Raid-bounded dispatch (Semaphore + drop) [PRESERVED]

The system MUST preserve the shipped per-guild bound in `GreetingService.dispatch_greeting` (verified: `bot/services/greeting_service.py:31 RAID_MAX_CONCURRENT=2 "(D4 raid guard)"`, `:57 _raid_semaphores: dict[str, Semaphore]`, `:200-201 locked() guard + WARNING "greeting dropped: raid saturation guild=%s"` then `async with sem`, `:214 asyncio.to_thread(render_fn, ...)`; `evict_guild_sync` at `:101`). Acquisition MUST be non-blocking drop (not queue); 100 concurrent joins MUST NOT produce 100 concurrent `to_thread` renders. Regression guard: `tests/test_greeting_service_raid.py::test_semaphore_is_guild_scoped` and `test_burst_caps_concurrency_and_drops_excess` (peak 2, drops=4) MUST stay green.

#### Scenario: Concurrent burst is bounded

- GIVEN 100 `on_member_join` events fire concurrently for guild G
- WHEN `dispatch_greeting` runs
- THEN at most 2 renders execute concurrently per guild; excess drop with WARNING

#### Scenario: Saturation drops do not error

- GIVEN semaphore for G is saturated (2 slots held)
- WHEN another `dispatch_welcome` arrives
- THEN it returns early without exception and without enqueue

#### Scenario: Render still off event loop

- GIVEN a welcome dispatch proceeds (slot acquired)
- WHEN renderer is invoked
- THEN call is wrapped in `asyncio.to_thread` and Pillow does not block loop

#### Scenario: Eviction on guild leave

- GIVEN a guild semaphore exists in `_raid_semaphores`
- WHEN `GreetingService.evict_guild_sync(guild_id)` runs via `on_guild_remove`
- THEN entry is removed (no RAM leak)
