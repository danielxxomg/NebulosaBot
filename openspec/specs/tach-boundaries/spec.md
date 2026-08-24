# Tach Boundaries Specification

## Purpose

Enforce NebulosaBot's layered module architecture via `tach.toml` so import boundaries are machine-checked. Baseline captures the CURRENT architecture — NOT a pretext for refactoring.

## Requirements

### Requirement: tach.toml defines seven-layer architecture

`tach.toml` in repo root MUST define `layers = ["cogs", "views", "services", "utils", "core", "db", "models"]`. Higher layers MAY depend on lower; lower MUST NOT depend on higher. `source_roots = ["."]`.

#### Scenario: Seven layers declared in order

- GIVEN `tach.toml` exists
- WHEN `layers` is inspected
- THEN it contains exactly the seven layers in order

#### Scenario: views do not import services

- GIVEN views depends_on `["utils", "core", "models"]`
- WHEN a views file imports `bot.services.*`
- THEN `tach check` reports a violation

#### Scenario: services do not import cogs or views

- GIVEN services depends_on `["core", "db", "models", "utils"]`
- WHEN a services file imports `bot.cogs.*` or `bot.views.*`
- THEN `tach check` reports a violation

#### Scenario: models depend on nothing

- GIVEN models `depends_on = []`
- WHEN `tach check` runs
- THEN any model importing another layer reports a violation

### Requirement: Renderer split stays in the services layer

The renderer modules `RankRenderer`, `GreetingRenderer`, and the shared `shared_assets` module MUST live in the `bot/services/` package (services layer); the retired compatibility shim is deleted and MUST NOT be reintroduced. The Cycle 2 neon theme branch of `PillowGreetingRenderer` MUST also live in the services layer (it is part of the existing `GreetingRenderer` module, not a new module). `shared_assets` MUST NOT import cogs or views. The renderers MUST NOT import cogs or views. The existing services-layer rule (services depend on `["core", "db", "models", "utils"]`) MUST continue to hold for the new modules and the neon branch.
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

### Requirement: Module declarations match real architecture

`tach.toml` MUST declare `[[modules]]` for each bot/ subpackage
(`bot.cogs`, `bot.views`, `bot.services`, `bot.utils`, `bot.core`,
`bot.core.db`, `bot.models`, `bot.listeners`) with `layer` matching the
hierarchy. `bot.listeners` belongs to `utils`. The image-service split
(`RankRenderer`, `GreetingRenderer`, `shared_assets`) is covered by the
existing `bot.services` module declaration and MUST NOT require new
top-level `[[modules]]` entries.

#### Scenario: cogs and core.db assigned to correct layers

- GIVEN `path = "bot.cogs"`, `layer = "cogs"` and `path = "bot.core.db"`, `layer = "db"`
- WHEN `tach check` runs
- THEN cogs are checked against cogs rules and db mixins MAY import models but not services

#### Scenario: Split modules covered by services declaration

- GIVEN `RankRenderer`, `GreetingRenderer`, and `shared_assets` under `bot.services`
- WHEN `tach check` runs
- THEN they are checked under the existing `bot.services` declaration with no new top-level module entry required

### Requirement: utils→services violation resolved

The violation at `bot/utils/ticket_helpers.py:17` (importing `parse_ticket_ref` from `bot.services.ticket_invariants`) MUST be resolved by: (a) moving `parse_ticket_ref` and `TicketRef` to `bot/core/` or `bot/models/` (preferred), OR (b) marking `deprecated = true` with a documented migration. MUST NOT be `unchecked = true`.

#### Scenario: parse_ticket_ref moved to lower layer

- GIVEN `parse_ticket_ref` relocated to `bot/core/` or `bot/models/`
- WHEN `tach check` runs
- THEN utils imports it without a violation

#### Scenario: Deprecated dependency warns

- GIVEN utils→services marked `deprecated = true`
- WHEN `tach check` runs
- THEN tach warns but does not fail

### Requirement: Strict enforcement flags enabled

`tach.toml` MUST set `exact = true`, `forbid_circular_dependencies = true`, `ignore_type_checking_imports = true`, `respect_gitignore = true`.

#### Scenario: exact mode flags unused dependencies

- GIVEN a module declares a depends_on entry no file imports
- WHEN `tach check --exact` runs
- THEN tach reports the unused dependency

#### Scenario: Circular dependency and TYPE_CHECKING handling

- GIVEN two modules import each other, OR a module imports another only inside `TYPE_CHECKING`
- WHEN `tach check` runs
- THEN circular imports report errors, and TYPE_CHECKING imports are NOT flagged

### Requirement: Interfaces for ticket invariants

`tach.toml` MUST declare `[[interfaces]]` exposing the ticket-domain public surface (`parse_ticket_ref`, `TicketRef`, `Ticket`) from their owning module.

#### Scenario: Public interface enforced

- GIVEN `expose = ["parse_ticket_ref", "TicketRef"] from = ["bot.core.ticket_ref"]`
- WHEN a module imports a non-exposed member
- THEN `tach check` reports an interface violation

### Requirement: tach check and check-external in CI and pre-push

`tach check` and `tach check-external` MUST run in the CI quality job and pre-push prek stage. Both blocking.

#### Scenario: CI and pre-push run tach blocking

- GIVEN CI quality job and pre-push stage include `tach check` and `tach check-external`
- WHEN a boundary or external-dependency violation exists during CI or `git push`
- THEN the quality job fails, or the push is aborted

### Requirement: Baseline captures current architecture

Baseline MUST capture architecture at PR6 time. MUST NOT reshape modules (S3 ticket_service decomposition out of scope).

#### Scenario: Baseline green, new violations caught

- GIVEN `tach.toml` matches the real import graph (after resolving the violation)
- WHEN `tach check` runs, then a developer adds a models→cogs import
- THEN the baseline run exits zero and the new import is reported as a violation


<!-- BEGIN DELTA: welcome-neon-timer-banana (tach-boundaries) -->

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
<!-- END DELTA: welcome-neon-timer-banana (tach-boundaries) -->
