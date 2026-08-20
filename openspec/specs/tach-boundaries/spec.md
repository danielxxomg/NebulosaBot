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

### Requirement: Module declarations match real architecture

`tach.toml` MUST declare `[[modules]]` for each bot/ subpackage (`bot.cogs`, `bot.views`, `bot.services`, `bot.utils`, `bot.core`, `bot.core.db`, `bot.models`, `bot.listeners`) with `layer` matching the hierarchy. `bot.listeners` belongs to `utils`.

#### Scenario: cogs and core.db assigned to correct layers

- GIVEN `path = "bot.cogs"`, `layer = "cogs"` and `path = "bot.core.db"`, `layer = "db"`
- WHEN `tach check` runs
- THEN cogs are checked against cogs rules and db mixins MAY import models but not services

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
