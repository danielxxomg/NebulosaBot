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

<!-- BEGIN DELTA: ticket-physical-split S3 -->

### Requirement: `is_mod` dual-path characterization

The system MUST preserve the existing `is_mod` decorator path and `is_mod_check` inline path without changing permission decisions. Characterization coverage MUST account for 24 `@is_mod()` decorator applications (16 in `tickets.py` and 8 in `sentinel.py`) and every inline `is_mod_check` call, including persistent and ephemeral ticket view callbacks. The `unclaim` command intentionally has no `@is_mod()` decorator and is gated by an inline `is_mod_check` (claimer-or-mod) — it is not counted as a decorator. The `/delete_category` command's guard is changed to `@is_admin()` in Cycle 2, reducing the `@is_mod()` decorator count by one (24 → 23); the characterization MUST be updated to reflect this and the `is_admin()` guard MUST be characterized separately. The behavior MUST remain a single decision point in `bot/utils/checks.py`.
(Previously: characterization counted 24 `@is_mod()` decorator applications; Cycle 2 moves `delete_category` to `@is_admin()`, so the `@is_mod()` count drops to 23.)

#### Scenario: Both hybrid paths remain registered

- GIVEN a command is decorated with `@is_mod()`
- WHEN its checks are inspected
- THEN both prefix and slash predicates are registered

#### Scenario: Inline view checks remain fail-closed

- GIVEN a ticket view callback runs without a guild, role, or valid moderator context
- WHEN `is_mod_check` is evaluated
- THEN it denies without weakening the existing permission behavior

#### Scenario: Caller characterization passes after delete_category move

- GIVEN the 23 `@is_mod()` decorator applications (delete_category now `@is_admin()`) and all inline call sites are exercised
- WHEN the Cycle 2 permission test suite runs
- THEN all existing administrator, moderator, regular-user, and DM outcomes remain unchanged and the new `delete_category` mod-denied outcome passes

<!-- END DELTA: ticket-physical-split S3 -->

<!-- BEGIN DELTA: staging-live-parity S4 -->

### Requirement: Historical guild-scope ledger is separate from runtime truth

The 12 names formerly exposed as `GUILD_SCOPE_GAPS` MUST be renamed to `GUILD_SCOPE_GAP_HISTORY` and preserved as audit history. Reports and tests MUST expose a separate `guild_scope_runtime_closed` fact. That fact MUST equal 12 only when every listed database entry point enforces guild ownership; the historical tuple MUST NOT itself block or authorize runtime behavior.

#### Scenario: Historical rename preserves all entries

- GIVEN the ledger contains the 12 previously identified scope entries
- WHEN the S4 rename is applied
- THEN the historical name is used, all 12 entries remain, and no entry is silently deleted

#### Scenario: Runtime closure is truthful

- GIVEN all 12 entry points enforce guild ownership
- WHEN the permission/parity report is built
- THEN `guild_scope_runtime_closed` equals 12 and the historical ledger remains informational

#### Scenario: Partial enforcement does not claim closure

- GIVEN one or more listed entry points lacks an enforceable guild boundary
- WHEN the report is built
- THEN the runtime-closed value is below 12 or unresolved and acceptance cannot claim full closure

#### Scenario: Cross-guild access remains denied

- GIVEN equivalent identifiers exist in guilds A and B
- WHEN guild A invokes a listed database path for guild B's identifier
- THEN no guild B data is returned or mutated, regardless of the historical ledger name

<!-- END DELTA: staging-live-parity S4 -->

<!-- BEGIN DELTA: welcome-neon-timer-banana (permission-model) -->
## ADDED Requirements

### Requirement: delete_category requires administrator

The `/delete_category` command MUST be restricted to administrators via the
`@is_admin()` guard (replacing the current `@is_mod()` decorator on the
command at `bot/cogs/tickets.py:262`). Category deletion is a destructive
admin-only action; a moderator without the Administrator permission MUST be
denied. The command MUST keep its existing `@app_commands.default_permissions(administrator=True)`
hint and ephemeral responses. Strict TDD: a RED test exercising the mod-denied
branch MUST be added before the guard is changed, and the existing admin-
allowed and category-not-found/open-tickets behaviors MUST remain unchanged.
The `delete_category` *service* path (`bot/cogs/ticket_admin_flow.py:142`)
MUST continue to enforce guild-scoped access (the `row.get("guildId") != gid`
check); only the *command* guard changes from `is_mod` to `is_admin`.

#### Scenario: Administrator deletes a category

- GIVEN an administrator invokes `/delete_category` on a category with no open tickets
- WHEN the command executes
- THEN the category is removed and a confirmation is shown ephemerally

#### Scenario: Moderator denied

- GIVEN a moderator (mod role, no Administrator permission) invokes `/delete_category`
- WHEN the `@is_admin()` guard evaluates
- THEN access is denied and no category is removed

#### Scenario: RED test precedes the guard change

- GIVEN the guard is still `is_mod()`
- WHEN the new mod-denied test is run before the guard change
- THEN the test FAILS (proving it tests the new behavior); after the guard changes to `is_admin()`, the mod is denied and the test passes

#### Scenario: Service guild-scope check unchanged

- GIVEN the `delete_category` service path after the guard change
- WHEN a cross-guild category id is supplied
- THEN the existing `row.get("guildId") != gid` deny still fires and no foreign-guild category is deleted
<!-- END DELTA: welcome-neon-timer-banana (permission-model) -->

<!-- BEGIN DELTA: voice-moderation-permissions (permission-model) -->
## ADDED Requirements

### Requirement: Permission matrix resolver

The system MUST provide an `async def can(permission, ctx) -> bool` resolver in `bot/utils/checks.py` that evaluates a permission against the guild's `permissionMatrix` JSONB column. The resolver MUST read the matrix from the cached `GuildConfig` (riding the existing `{guild_id}:config` cache entry — no new cache key, no bare `perm_matrix` entity string). The decision order MUST be: DM invocation (no guild) → deny; guild administrator (`ctx.author.guild_permissions.administrator`) → True; matrix key present for the permission → True if the user holds any role listed in `matrix[permission]`, else deny (no fallback); `moderation.*` permission with absent matrix key → fall back to the configured `modRoleId` (True if user holds mod role, else deny); any other permission with absent matrix key → deny (deny-default). The resolver MUST return False for unknown permission names (not in the `PERMISSIONS` frozenset). The `PERMISSIONS` frozenset MUST contain exactly seven permissions: `moderation.warn`, `moderation.mute`, `moderation.kick`, `moderation.ban`, `tickets.manage`, `economy.manage`, `greeting.manage`.

#### Scenario: Administrator implicitly passes

- GIVEN a user with the Administrator permission
- WHEN `can("moderation.ban", ctx)` is evaluated
- THEN it returns True without consulting the matrix

#### Scenario: Matrix role grants permission

- GIVEN a guild's `permissionMatrix` maps `moderation.ban` to `["roleA"]`
- WHEN a user holding roleA invokes `can("moderation.ban", ctx)`
- THEN it returns True

#### Scenario: Moderation fallback to modRoleId

- GIVEN a guild has `modRoleId` configured and no `moderation.ban` key in `permissionMatrix`
- WHEN a user holding the mod role invokes `can("moderation.ban", ctx)`
- THEN it returns True (moderation.* fallback)

#### Scenario: Regular user denied when matrix key present

- GIVEN a guild's `permissionMatrix` maps `moderation.ban` to `["roleA"]`
- WHEN a user without roleA invokes `can("moderation.ban", ctx)`
- THEN it returns False (no fallback when key is present)

#### Scenario: Unconfigured permission denies

- GIVEN a guild with `permissionMatrix = {}` and no `modRoleId`
- WHEN `can("greeting.manage", ctx)` is evaluated (non-moderation, no key)
- THEN it returns False

#### Scenario: Unknown permission denies

- GIVEN any guild configuration
- WHEN `can("nonexistent.perm", ctx)` is evaluated
- THEN it returns False

#### Scenario: DM invocation denies

- GIVEN a user invokes a permission check in a DM (no guild context)
- WHEN `can_member("moderation.ban", member, guild_id)` is called with no guild
- THEN it returns False

#### Scenario: Cache isolation prevents cross-guild leak

- GIVEN guild A's `permissionMatrix` grants `moderation.ban` to roleX and guild B does not
- WHEN a user with roleX is evaluated in guild B
- THEN `can("moderation.ban", ctx)` returns False (guild-scoped, no leak)

#### Scenario: All seven permissions resolvable

- GIVEN a guild's matrix grants a role to each of the seven permissions
- WHEN the user holding that role is evaluated for each permission
- THEN `can()` returns True for all seven: `moderation.warn`, `moderation.mute`, `moderation.kick`, `moderation.ban`, `tickets.manage`, `economy.manage`, `greeting.manage`

### Requirement: Permission check decorator dual registration

The system MUST provide a `can_check(permission)` decorator in `bot/utils/checks.py` that mirrors the `is_admin()` dual-path shape: `commands.check(_prefix_predicate)(app_commands.check(_app_predicate)(func))`. Every hybrid command decorated with `@can_check(permission)` MUST have non-empty `cmd.checks` (prefix path) AND non-empty `app_command.checks` (slash path). The decorator MUST expose `.predicate` and `.prefix_predicate` for testability. The system MUST also provide an `async def can_member(permission, member, guild_id) -> bool` listener form mirroring `can()` (admin pass, matrix grant, moderation fallback, deny) for callers without a `Context` (e.g. ticket view callbacks).

#### Scenario: Dual registration proof

- GIVEN a hybrid command decorated with `@can_check("moderation.ban")`
- WHEN inspecting the command's checks
- THEN `cmd.checks` (prefix) is non-empty AND `app_command.checks` (slash) is non-empty

#### Scenario: Listener form mirrors resolver

- GIVEN `can_member("moderation.ban", member, guild_id)` is called
- WHEN the member is an administrator, holds a matrix-granted role, holds the modRoleId (moderation fallback), or lacks all
- THEN it returns the same value `can()` would for the equivalent `ctx`

## MODIFIED Requirements

### Requirement: Ban command requires administrator

The `/ban` command MUST be restricted via `@can_check("moderation.ban")` (replacing the prior `@is_admin()` guard). The command MUST preserve its `ConfirmCancelView` ephemeral confirmation flow and `@app_commands.default_permissions(ban_members=True)` hint. An administrator MUST pass implicitly (admin implicit pass in `can()`). A user granted `moderation.ban` via the guild's `permissionMatrix` MUST pass. A user with only the configured `modRoleId` MUST pass (moderation.* fallback when no matrix key). A user without matrix grant, mod role, or administrator permission MUST be denied on both prefix and slash paths.

(Previously: `/ban` was restricted to administrators via `@is_admin()`.)

#### Scenario: Administrator invokes ban

- GIVEN a user has the Administrator permission
- WHEN they invoke `/ban` and click Confirm
- THEN the command executes

#### Scenario: Matrix-granted role invokes ban

- GIVEN a guild's `permissionMatrix` maps `moderation.ban` to roleA and the user holds roleA
- WHEN they invoke `/ban` and click Confirm
- THEN the command executes (matrix grant path)

#### Scenario: Moderator without matrix key invokes ban

- GIVEN a guild has `modRoleId` configured and no `moderation.ban` matrix key
- WHEN a mod-role user invokes `/ban` and clicks Confirm
- THEN the command executes (moderation.* fallback)

#### Scenario: Non-authorized user denied

- GIVEN a user without administrator, matrix grant, or mod role
- WHEN they invoke `/ban`
- THEN access is denied on both prefix and slash paths

#### Scenario: ConfirmCancelView preserved

- GIVEN the `/ban` command after re-gating
- WHEN an authorized user invokes it
- THEN the ephemeral `ConfirmCancelView` (target, reason, delete_days, Confirm/Cancel) is shown before any action

### Requirement: Moderator check

The system MUST preserve the `is_mod` decorator's dual-path enforcement and external outcomes (admin pass, modRoleId pass, deny-default). The `is_mod` shim MUST honor `moderation.*` matrix keys when present: a matrix key for the relevant `moderation.*` permission MUST grant via role intersect, falling back to `modRoleId` only when the key is absent. The prefix path MUST continue to raise `NoPrivateMessage` in DMs, `MissingRole` when configured but lacking, and `CheckFailure` when unconfigured and non-admin. The slash path behavior MUST remain equivalent to the current `is_mod_check` decision logic — no regression.

(Previously: `is_mod` described role/admin evaluation; did not consult the permission matrix. Cycle 2 added dual-path enforcement. This delta adds matrix-key awareness via the `_is_mod_via_matrix` helper.)

#### Scenario: Matrix key grants via is_mod

- GIVEN a guild's matrix maps `moderation.warn` to roleA and the user holds roleA
- WHEN `is_mod` evaluates a command guarded with `@is_mod()`
- THEN it returns True (matrix path)

#### Scenario: is_mod falls back to modRoleId when matrix key absent

- GIVEN a guild has `modRoleId` configured and no `moderation.*` matrix keys
- WHEN a mod-role user invokes an `@is_mod()` guarded command
- THEN it returns True (fallback path, unchanged)

#### Scenario: is_mod denies when matrix key present and role absent

- GIVEN a guild's matrix maps `moderation.warn` to roleA and the user lacks roleA
- WHEN `is_mod` evaluates
- THEN it returns False (deny-default when key present)

#### Scenario: is_mod external outcomes unchanged

- GIVEN the 23 `@is_mod()` decorator applications and all inline `is_mod_check` call sites
- WHEN the permission test suite runs
- THEN all existing admin, moderator, regular-user, and DM outcomes remain unchanged
<!-- END DELTA: voice-moderation-permissions (permission-model) -->

