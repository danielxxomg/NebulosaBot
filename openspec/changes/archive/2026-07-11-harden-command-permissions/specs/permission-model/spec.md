# Delta for Permission Model

## MODIFIED Requirements

### Requirement: Moderator check

The system MUST provide an `is_mod` check that gates BOTH the prefix (`commands.check`) and slash (`app_commands.check`) invocation paths. The check MUST register both predicates so that every hybrid command decorated with `@is_mod()` inherits dual-path enforcement without per-command changes.

The prefix path MUST return true for users with the configured moderator role OR the Administrator permission. The prefix path MUST raise `NoPrivateMessage` when invoked in DMs. The prefix path MUST raise `MissingRole` when the mod role is configured but the user lacks it. The prefix path MUST raise `CheckFailure` when no mod role is configured and the user is not an administrator.

The slash path behavior MUST remain equivalent to the current `is_mod_check` decision logic — no regression.

(Previously: Only described role/admin evaluation logic; did not enforce dual-path registration. Implementation only gated slash path.)

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

(Previously: Only described slash-path fallback; prefix path had no enforcement at all.)

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
