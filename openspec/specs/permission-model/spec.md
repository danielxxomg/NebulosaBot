# Permission Model Specification

## Purpose

Define permission checks for moderators and administrators.

## Requirements

### Requirement: Administrator check

The system MUST provide an `is_admin` check that returns true for guild administrators.

#### Scenario: Admin user

- GIVEN a user with the Administrator permission
- WHEN `is_admin` is evaluated
- THEN it returns true

#### Scenario: Non-admin user

- GIVEN a user without the Administrator permission
- WHEN `is_admin` is evaluated
- THEN it returns false

### Requirement: Moderator check

The system MUST provide an `is_mod` check that gates BOTH the prefix (`commands.check`) and slash (`app_commands.check`) invocation paths. The check MUST register both predicates so that every hybrid command decorated with `@is_mod()` inherits dual-path enforcement without per-command changes.

The prefix path MUST return true for users with the configured moderator role OR the Administrator permission. The prefix path MUST raise `NoPrivateMessage` when invoked in DMs. The prefix path MUST raise `MissingRole` when the mod role is configured but the user lacks it. The prefix path MUST raise `CheckFailure` when no mod role is configured and the user is not an administrator.

The slash path behavior MUST remain equivalent to the current `is_mod_check` decision logic — no regression.

#### Scenario: Mod role via slash

- GIVEN a guild has configured a moderator role
- WHEN a user with that role invokes a guarded command via slash
- THEN `is_mod` returns true

#### Scenario: Admin fallback via slash

- GIVEN a guild has no moderator role configured
- WHEN an administrator invokes a guarded command via slash
- THEN `is_mod` returns true

#### Scenario: Regular user via slash

- GIVEN a user without the moderator role or Administrator permission
- WHEN `is_mod` is evaluated via slash
- THEN it returns false

#### Scenario: Mod role via prefix

- GIVEN a guild has configured a moderator role
- WHEN a user with that role invokes a guarded command via prefix
- THEN the command executes successfully

#### Scenario: Admin via prefix

- GIVEN a guild has a moderator role configured
- WHEN an administrator invokes a guarded command via prefix
- THEN the command executes successfully (admin always passes)

#### Scenario: Regular user via prefix denied

- GIVEN a user without the moderator role or Administrator permission
- WHEN they invoke a guarded command via prefix
- THEN `MissingRole` is raised (configured role exists but user lacks it)

#### Scenario: DM invocation denied

- GIVEN a user invokes a guarded command via DM (no guild context)
- WHEN `is_mod` prefix predicate evaluates
- THEN `NoPrivateMessage` is raised

#### Scenario: Dual registration proof

- GIVEN any hybrid command decorated with `@is_mod()`
- WHEN inspecting the command's checks
- THEN `cmd.checks` (prefix) is non-empty AND `app_command.checks` (slash) is non-empty

### Requirement: Unconfigured moderator role

The system SHOULD fall back to administrator-only access when no moderator role is configured. This applies to BOTH prefix and slash invocation paths — deny-by-default for non-administrators.

#### Scenario: Missing mod role via slash

- GIVEN no moderator role is set
- WHEN a non-administrator user invokes a moderator-guarded command via slash
- THEN access is denied

#### Scenario: Missing mod role via prefix

- GIVEN no moderator role is set
- WHEN a non-administrator user invokes a moderator-guarded command via prefix
- THEN `CheckFailure` is raised with a message indicating no moderator role is configured

#### Scenario: Admin passes when unconfigured via prefix

- GIVEN no moderator role is set
- WHEN an administrator invokes a moderator-guarded command via prefix
- THEN the command executes successfully

### Requirement: Ban command requires administrator

The `/ban` command MUST be restricted to administrators via the `@is_admin()` guard.

#### Scenario: Admin invokes ban

- GIVEN a user has the Administrator permission
- WHEN they invoke `/ban`
- THEN the command executes

#### Scenario: Moderator invokes ban

- GIVEN a user has the moderator role but not the Administrator permission
- WHEN they invoke `/ban`
- THEN access is denied

<!-- BEGIN DELTA: refactor-ticket-domain (permission-model) -->
## ADDED Requirements

### Requirement: Typed hybrid command context

Sentinel and Utility hybrid command callbacks and helpers MUST use `NebulosaContext` or an explicitly typed `commands.Context[NebulosaBot]`. They MUST preserve access to `Context.interaction` for slash-aware behavior and MUST NOT silence the S2 typing debt with broad `Any` annotations or unscoped ignores.

#### Scenario: Test typing debt is closed

- GIVEN the baseline has 28 mypy errors across seven test files
- WHEN the S2.1 type fixes and annotations are checked
- THEN `mypy bot tests` reports zero errors without broad suppression

#### Scenario: Hybrid interaction remains available

- GIVEN a hybrid command receives a `NebulosaContext`
- WHEN its callback needs slash interaction data
- THEN `context.interaction` remains available with the expected optional typing

### Requirement: `is_mod` dual-path characterization

The system MUST preserve the existing `is_mod` decorator path and `is_mod_check` inline path without changing permission decisions. Characterization coverage MUST account for the 23 decorator callers and 21 inline callers, including persistent and ephemeral ticket view callbacks.

#### Scenario: Both hybrid paths remain registered

- GIVEN a command is decorated with `@is_mod()`
- WHEN its checks are inspected
- THEN both prefix and slash predicates are registered

#### Scenario: Inline view checks remain fail-closed

- GIVEN a ticket view callback runs without a guild, role, or valid moderator context
- WHEN `is_mod_check` is evaluated
- THEN it denies without weakening the existing permission behavior

#### Scenario: Caller characterization passes

- GIVEN the 23 decorator and 21 inline call sites are exercised
- WHEN the S2.1 permission test suite runs
- THEN all existing admin, moderator, regular-user, and DM outcomes remain unchanged

<!-- END DELTA: refactor-ticket-domain (permission-model) -->
