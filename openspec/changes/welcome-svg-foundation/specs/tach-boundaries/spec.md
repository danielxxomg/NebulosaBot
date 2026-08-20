# Delta for Tach Boundaries

Cycle 1. The image-service SRP split adds new service modules
(`RankRenderer`, `GreetingRenderer`, `shared_assets`). These MUST land in the
`services` layer and MUST NOT introduce cross-layer violations. This delta
adds scenarios governing the split so `tach check` stays green.

## ADDED Requirements

### Requirement: Image-service split stays in the services layer

The split of `ImageService` into `RankRenderer`, `GreetingRenderer`, and a
`shared_assets` module MUST place all three in the `bot/services/` package
(services layer). `shared_assets` MUST NOT import cogs or views. The renderers
MUST NOT import cogs or views. The existing services-layer rule (services
depend on `["core", "db", "models", "utils"]`) MUST continue to hold for the
new modules.

#### Scenario: Renderers and shared assets are services

- GIVEN the split files under `bot/services/`
- WHEN `tach check` runs
- THEN `RankRenderer`, `GreetingRenderer`, and `shared_assets` are all classified in the `services` layer

#### Scenario: No services-layer upward import

- GIVEN the new service modules
- WHEN scanned for imports of `bot.cogs.*` or `bot.views.*`
- THEN zero matches are found and `tach check` reports no violation

### Requirement: cache_key helper stays in the utils layer

The `cache_key(guild_id, entity)` helper MUST remain in the `utils` layer
(`bot/utils/cache.py`). New service-layer caches (e.g. a Cycle 2 greeting
avatar cache) MUST import `cache_key` from utils; the helper MUST NOT be
copied into a service module. This keeps the guild-scoping contract in one
place so a leaked bare-key implementation cannot bypass it.

#### Scenario: cache_key is imported, not duplicated

- GIVEN any new cache introduced by the split
- WHEN its key construction is inspected
- THEN it imports `cache_key` from `bot.utils.cache` and does not redefine it

### Requirement: Interface injection does not cross layers

`bot/bot.py` (core) injects the concrete `GreetingRenderer` into
`GreetingService` (services). The services layer MUST depend on a renderer
interface, not on a concrete renderer imported from a higher layer. The
concrete Pillow renderer MUST live in the services layer so the injection
stays intra-layer.

#### Scenario: Concrete renderer lives in services

- GIVEN `PillowGreetingRenderer`
- WHEN its module location is inspected
- THEN it is under `bot/services/` and the services layer does not import from `cogs` or `views` to obtain it

## MODIFIED Requirements

### Requirement: Module declarations match real architecture

`tach.toml` MUST declare `[[modules]]` for each bot/ subpackage
(`bot.cogs`, `bot.views`, `bot.services`, `bot.utils`, `bot.core`,
`bot.core.db`, `bot.models`, `bot.listeners`) with `layer` matching the
hierarchy. `bot.listeners` belongs to `utils`. The image-service split
(`RankRenderer`, `GreetingRenderer`, `shared_assets`) is covered by the
existing `bot.services` module declaration and MUST NOT require new
top-level `[[modules]]` entries.

(Previously: the requirement covered the existing subpackages but did not
address the image-service split.)

#### Scenario: cogs and core.db assigned to correct layers

- GIVEN `path = "bot.cogs"`, `layer = "cogs"` and `path = "bot.core.db"`, `layer = "db"`
- WHEN `tach check` runs
- THEN cogs are checked against cogs rules and db mixins MAY import models but not services

#### Scenario: Split modules covered by services declaration

- GIVEN `RankRenderer`, `GreetingRenderer`, and `shared_assets` under `bot.services`
- WHEN `tach check` runs
- THEN they are checked under the existing `bot.services` declaration with no new top-level module entry required

## Scope boundary

This delta governs only the layer placement of the Cycle 1 split. Reshaping
the architecture, adding new layers, or decomposing other services (e.g. the
S3 `ticket_service` decomposition) is OUT OF SCOPE and remains excluded by the
existing "Baseline captures current architecture" requirement. Cycle 2/3
scope (Neon, timer, 12h, banana, RLS, voice/moderation, ScheduledAction,
has_perm) is OUT OF SCOPE.
