# Delta for Permission Model

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
