# Delta for permission-model

## MODIFIED Requirements

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
