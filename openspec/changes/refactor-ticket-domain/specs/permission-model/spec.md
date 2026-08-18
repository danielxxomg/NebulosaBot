# Delta for Permission Model

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
