# Delta for Tach Boundaries

Cycle 2 of 3. Extends the seven-layer `tach.toml` boundary contract to the new
Cycle 2 modules: `OcioService` lives in the `services` layer (no upward
imports), the neon branch of `PillowGreetingRenderer` stays in the `services`
layer, `format_remaining` lives in `bot/utils/time.py` (utils layer, the
duration domain), and the greeting avatar cache imports `cache_key` from utils
(it MUST NOT redefine it). The baseline captures the CURRENT architecture;
this delta only adds coverage for the new modules, not a reshaping.

## ADDED Requirements

### Requirement: OcioService stays in the services layer

`OcioService` MUST live in the `bot/services/` package (services layer). It
MUST NOT import `bot.cogs.*` or `bot.views.*`. It MUST NOT import Discord
command/view types for its pure-logic methods (`get_random_banana`,
`get_8ball_response`); those methods MUST be unit-testable without Discord
mocks. The services-layer rule (services depend on
`["core", "db", "models", "utils"]`) MUST continue to hold for `OcioService`.
Pillow work in `OcioService` (the banana fallback) MUST call `asyncio.to_thread`
and the import of Pillow MAY live in the service module.

#### Scenario: OcioService is a services-layer module

- GIVEN `OcioService` is added under `bot/services/`
- WHEN `tach check` runs
- THEN it is classified in the `services` layer and depends only on `core`/`db`/`models`/`utils`

#### Scenario: OcioService has no upward imports

- GIVEN the `OcioService` module
- WHEN scanned for `bot.cogs.*` or `bot.views.*` imports
- THEN zero matches are found and `tach check` reports no violation

### Requirement: format_remaining lives in the utils duration domain

`format_remaining(seconds) -> str` MUST live in `bot/utils/time.py` (utils
layer, the duration domain) alongside `parse_duration` and
`parse_duration_strict`. It MUST NOT live in a cog, view, or service, and MUST
NOT be duplicated. The ticket timer cog/service imports it from
`bot.utils.time`. This keeps duration formatting in one place consistent with
the `time.py`/`timeparse.py` separation contract.

#### Scenario: format_remaining is in utils/time.py

- GIVEN the Cycle 2 change is applied
- WHEN `bot/utils/time.py` is inspected
- THEN `format_remaining` is defined there and importable as `from bot.utils.time import format_remaining`

#### Scenario: format_remaining not duplicated in cogs/services

- GIVEN the cog and service files that use `format_remaining`
- WHEN they are scanned for a local `def format_remaining`
- THEN zero local definitions exist and all import from `bot.utils.time`

## MODIFIED Requirements

### Requirement: Image-service split stays in the services layer

The split of `ImageService` into `RankRenderer`, `GreetingRenderer`, and a `shared_assets` module MUST place all three in the `bot/services/` package (services layer). The Cycle 2 neon theme branch of `PillowGreetingRenderer` MUST also live in the services layer (it is part of the existing `GreetingRenderer` module, not a new module). `shared_assets` MUST NOT import cogs or views. The renderers MUST NOT import cogs or views. The existing services-layer rule (services depend on `["core", "db", "models", "utils"]`) MUST continue to hold for the new modules and the neon branch.
(Previously: the requirement covered the Cycle 1 three-way split; it did not name the Cycle 2 neon theme branch.)

#### Scenario: Renderers and shared assets are services

- GIVEN the split files under `bot/services/` including the neon branch
- WHEN `tach check` runs
- THEN `RankRenderer`, `GreetingRenderer` (with neon branch), and `shared_assets` are all classified in the `services` layer

#### Scenario: No services-layer upward import

- GIVEN the new service modules and the neon branch
- WHEN scanned for imports of `bot.cogs.*` or `bot.views.*`
- THEN zero matches are found and `tach check` reports no violation

### Requirement: cache_key helper stays in the utils layer

The `cache_key(guild_id, entity)` helper MUST remain in the core layer (`bot/core/cache.py`). New service-layer caches (including the Cycle 2 greeting avatar cache) MUST import `cache_key` from `bot.core.cache`; the helper MUST NOT be copied into a service module. The Cycle 2 greeting avatar cache MUST use `cache_key(gid, "greeting_avatar")` and MUST NOT build the `{guild_id}:greeting_avatar` key inline. This keeps the guild-scoping contract in one place so a leaked bare-key implementation cannot bypass it.
(Previously: the requirement named a "Cycle 2 greeting avatar cache" as an example; Cycle 2 actually introduces it, so this delta makes the avatar cache a concrete governed cache.)

#### Scenario: cache_key is imported, not duplicated

- GIVEN the Cycle 2 greeting avatar cache introduced by the split
- WHEN its key construction is inspected
- THEN it imports `cache_key` from `bot.core.cache` and does not redefine it

#### Scenario: Avatar cache key is guild-scoped via the helper

- GIVEN the greeting avatar cache builds a key for guild G
- WHEN the key is constructed
- THEN it calls `cache_key(gid, "greeting_avatar")` producing `{gid}:greeting_avatar`, not a bare `"greeting_avatar"` key

## Scope boundary

This delta only extends the boundary contract to the new Cycle 2 modules
(`OcioService`, neon branch, `format_remaining`, avatar cache). It does NOT
reshape modules or add new top-level `[[modules]]` entries — the new modules
are covered by the existing `bot.services` and `bot.utils` declarations. Cycle
3 (voice/moderation, ScheduledAction, has_perm) is OUT OF SCOPE.
