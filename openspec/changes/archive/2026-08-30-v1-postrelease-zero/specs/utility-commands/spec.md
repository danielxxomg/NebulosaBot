# Delta for utility-commands

## MODIFIED Requirements

### Requirement: Avatar command

The system MUST provide a slash-only `/avatar [member]` command via `@app_commands.command()` (MUST NOT use `hybrid_command`; prefix inert via `get_prefix -> []`) that displays the target user's avatar as a full-size embed image using `set_image` with `?size=1024`. Errors MUST use `t()`.

(Previously: purpose described hybrid commands; command was implicitly hybrid)

#### Scenario: Self avatar

- GIVEN a member invokes `/avatar` without target via slash
- WHEN the command executes
- THEN the embed image is the invoker's avatar URL with `?size=1024` via `set_image`

#### Scenario: Mentioned member avatar

- GIVEN a member invokes `/avatar @member` via slash
- WHEN the command executes
- THEN the embed image is the mentioned member's avatar URL

#### Scenario: Prefix inert

- GIVEN a user sends `nb!avatar` as text
- WHEN the message is processed
- THEN no command is invoked

### Requirement: Server info command

The system MUST provide a slash-only `/serverinfo` command via `@app_commands.command()` that returns a guild summary embed (name, owner, member count, channel count, role count, creation date). DM errors MUST use `t()`.

(Previously: implicitly hybrid via purpose)

#### Scenario: Guild context

- GIVEN the command is invoked inside a guild via slash
- WHEN the command executes
- THEN an embed shows name, owner mention, members, channels, roles, creation timestamp

#### Scenario: DM context

- GIVEN the command is invoked in a DM via slash
- WHEN the command executes
- THEN an error embed via `t()` states it only works in servers

### Requirement: User info command

The system MUST provide a slash-only `/userinfo [member]` command via `@app_commands.command()` that returns a member summary embed with name, ID, roles, join date, and account creation date. Prefix inert.

(Previously: implicitly hybrid)

#### Scenario: Member with few roles

- GIVEN a member invokes `/userinfo` via slash on a member with ≤20 roles
- WHEN the command executes
- THEN an embed lists all roles plus join and creation dates

#### Scenario: Member with many roles

- GIVEN a member invokes `/userinfo` via slash on a member with >20 roles
- WHEN the command executes
- THEN an embed lists the first 20 roles followed by "and N more"
