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

`is_mod` MUST gate via `app_commands.check` only for slash commands (no `commands.check`; prefix inert `get_prefix=[]` per `bot-core`). It MUST register its predicate for every slash command decorated with `@is_mod()`. Prefix predicate if retained is inert. The only surviving `hybrid_command` substrings after S1 are docstring examples at `bot/utils/checks.py:229,361` — AST scan for `hybrid_command`/`hybrid_group` decorators MUST be 0. `,` timer is `close-confirmation`, not a prefix.

(Previously: BOTH prefix+suffix dual path for hybrid; prefix raised `NoPrivateMessage`/`MissingRole`)

#### Scenario: Mod role via slash

- GIVEN guild has mod role and user has that role
- WHEN they invoke guarded command via slash
- THEN `is_mod` returns true

#### Scenario: Admin fallback via slash

- GIVEN no mod role configured
- WHEN administrator invokes via slash
- THEN `is_mod` returns true

#### Scenario: Regular user denied

- GIVEN user without mod role or admin
- WHEN they invoke via slash
- THEN `is_mod` returns false

#### Scenario: Slash-only registration

- GIVEN slash command decorated with `@is_mod()`
- WHEN checks inspected
- THEN `app_command.checks` non-empty and no hybrid decorator

### Requirement: Unconfigured moderator role

System SHOULD fall back to administrator-only when no mod role configured. Applies to slash path; prefix inert (`get_prefix=[]`).

(Previously: BOTH prefix and slash)

#### Scenario: Missing mod role via slash

- GIVEN no mod role set
- WHEN non-admin invokes via slash
- THEN denied via `t()`

#### Scenario: Admin passes when unconfigured

- GIVEN no mod role set
- WHEN administrator invokes via slash
- THEN command executes

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

### Requirement: `is_mod` slash-only characterization

The system MUST preserve the existing `is_mod` decorator path (slash-only `app_commands.check`, no `commands.check`; prefix inert) and `is_mod_check` inline path without changing permission decisions. Characterization coverage MUST account for the 23 decorator callers and 21 inline callers, including persistent and ephemeral ticket view callbacks.

#### Scenario: Slash-only registration

- GIVEN a command is decorated with `@is_mod()`
- WHEN its checks are inspected
- THEN the slash predicate is registered (``app_commands.check``) and no prefix predicate is registered

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

### Requirement: `is_mod` slash-only characterization

The system MUST preserve the existing `is_mod` decorator path (slash-only `app_commands.check`) and `is_mod_check` inline path without changing permission decisions. Characterization coverage MUST account for 24 `@is_mod()` decorator applications (16 in `tickets.py` and 8 in `sentinel.py`) and every inline `is_mod_check` call, including persistent and ephemeral ticket view callbacks. The `unclaim` command intentionally has no `@is_mod()` decorator and is gated by an inline `is_mod_check` (claimer-or-mod) — it is not counted as a decorator. The `/delete_category` command's guard is changed to `@is_admin()` in Cycle 2, reducing the `@is_mod()` decorator count by one (24 → 23); the characterization MUST be updated to reflect this and the `is_admin()` guard MUST be characterized separately. The behavior MUST remain a single decision point in `bot/utils/checks.py` with slash-only registration (no `commands.check`).
(Previously: characterization counted 24 `@is_mod()` decorator applications; Cycle 2 moves `delete_category` to `@is_admin()`, so the `@is_mod()` count drops to 23.)

#### Scenario: Slash-only registration

- GIVEN a command is decorated with `@is_mod()`
- WHEN its checks are inspected
- THEN the slash predicate is registered and no prefix predicate is registered

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

`can_check(permission)` in `bot/utils/checks.py` MUST gate slash commands via `app_commands.check` only (no `commands.check`; prefix inert). Every slash command with `@can_check` MUST have non-empty `app_command.checks` and zero hybrid decorators. It MUST expose `.predicate` for testability. `can_member` listener form MUST mirror `can()` (admin pass, matrix grant, moderation fallback, deny). `PERMISSIONS` MUST be exactly seven: `moderation.warn`, `moderation.mute`, `moderation.kick`, `moderation.ban`, `tickets.manage`, `economy.manage`, `greeting.manage` — no new key.

(Previously: `commands.check`+`app_commands.check` dual path for hybrid; both `cmd.checks` and `app_command.checks`)

#### Scenario: Slash-only registration proof

- GIVEN slash command with `@can_check("moderation.ban")`
- WHEN checks inspected
- THEN `app_command.checks` non-empty and no hybrid

#### Scenario: Listener mirrors resolver

- GIVEN `can_member("moderation.ban", member, guild_id)` called
- WHEN member is admin/matrix/fallback/none
- THEN returns same as `can()` for equivalent `ctx`

#### Scenario: Seven permissions only

- GIVEN guild grants each of seven permissions
- WHEN user with that role evaluated
- THEN `can()` true for all seven and no eighth key exists

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

`is_mod` shim MUST preserve slash-only outcomes (admin pass, modRoleId pass, deny-default via `t()`) and honor `moderation.*` matrix keys: key present → grant via role intersect else deny (no fallback); key absent → fallback to `modRoleId`. Prefix path inert; no `NoPrivateMessage` for slash. Behavior equivalent to `is_mod_check` — no regression. `,` timer remains `close-confirmation`.

(Previously: dual-path with prefix raises; did not consult matrix initially)

#### Scenario: Matrix grants via is_mod

- GIVEN matrix maps `moderation.warn` to roleA and user holds roleA
- WHEN `is_mod` evaluates via slash
- THEN returns True

#### Scenario: Fallback to modRoleId

- GIVEN `modRoleId` configured and no `moderation.*` keys
- WHEN mod-role user invokes via slash
- THEN returns True

#### Scenario: Deny when key present and role absent

- GIVEN matrix maps `moderation.warn` to roleA and user lacks roleA
- WHEN `is_mod` evaluates via slash
- THEN returns False

#### Scenario: External outcomes unchanged

- GIVEN 23 `@is_mod()` decorators and all inline `is_mod_check` sites
- WHEN permission suite runs via slash
- THEN outcomes unchanged
### Requirement: Setup surface reuses existing matrix keys — no new key

The `/setup` panel and its modules MUST NOT introduce any new permission-matrix key. The `PERMISSIONS` frozenset MUST remain exactly the seven existing permissions (`moderation.warn`, `moderation.mute`, `moderation.kick`, `moderation.ban`, `tickets.manage`, `economy.manage`, `greeting.manage`). Panel invocation visibility uses `default_permissions(administrator=True)` (relaxable by server admins via Integrations) and administrators pass implicitly; module-level mutations authorize through the EXISTING keys via the standard `can()`/`can_check()` path: `tickets.manage` gates Tickets-module actions, `greeting.manage` gates Welcome/Goodbye-module actions.

#### Scenario: Matrix key set is unchanged

- GIVEN `PERMISSIONS` after this change
- WHEN its contents are inspected
- THEN it contains exactly the seven pre-existing keys and no setup-panel key

#### Scenario: Administrator opens panel implicitly

- GIVEN a user with the Administrator permission
- WHEN they invoke `/setup`
- THEN the panel opens without consulting the matrix (admin implicit pass)

#### Scenario: Tickets module gated by tickets.manage

- GIVEN a relaxed-integration non-admin whose role holds `tickets.manage`
- WHEN they perform a Tickets-module mutation
- THEN it succeeds via the existing matrix grant path

#### Scenario: Welcome module denied without greeting.manage

- GIVEN a relaxed-integration non-admin whose role lacks `greeting.manage`
- WHEN they attempt a Welcome-module save
- THEN the action is denied ephemerally and nothing persists

