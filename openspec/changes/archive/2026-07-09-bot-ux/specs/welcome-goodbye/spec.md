# Delta for Welcome/Goodbye

## ADDED Requirements

### Requirement: Welcome config command group

The system MUST provide a `/welcome` hybrid command group with subcommands: `config` (show current settings), `channel` (set welcome channel), `toggle` (enable/disable welcome), and `message` (set template). All subcommands MUST be admin-gated via `@app_commands.default_permissions(administrator=True)`.

#### Scenario: Show welcome config

- GIVEN an admin invokes `/welcome config`
- WHEN the command executes
- THEN an ephemeral embed displays current welcome channel, toggle state, and message template

#### Scenario: Set welcome channel

- GIVEN an admin invokes `/welcome channel #general`
- WHEN the command executes
- THEN the welcome channel is updated to #general and the cache is invalidated

#### Scenario: Toggle welcome off

- GIVEN welcome is currently enabled
- WHEN an admin invokes `/welcome toggle`
- THEN welcome is disabled and a confirmation is shown

#### Scenario: Set welcome message template

- GIVEN an admin invokes `/welcome message Welcome {user} to {server}!`
- WHEN the command executes
- THEN the welcome message template is saved and cache invalidated

#### Scenario: Non-admin blocked

- GIVEN a non-admin user
- WHEN they invoke `/welcome config`
- THEN Discord blocks the command (permission hint)

### Requirement: Goodbye config command group

The system MUST provide a `/goodbye` hybrid command group with subcommands: `config` (show current settings), `channel` (set goodbye channel), `toggle` (enable/disable goodbye), and `message` (set template). All subcommands MUST be admin-gated via `@app_commands.default_permissions(administrator=True)`.

#### Scenario: Show goodbye config

- GIVEN an admin invokes `/goodbye config`
- WHEN the command executes
- THEN an ephemeral embed displays current goodbye channel, toggle state, and message template

#### Scenario: Set goodbye channel

- GIVEN an admin invokes `/goodbye channel #goodbye`
- WHEN the command executes
- THEN the goodbye channel is updated and cache invalidated

#### Scenario: Toggle goodbye off

- GIVEN goodbye is currently enabled
- WHEN an admin invokes `/goodbye toggle`
- THEN goodbye is disabled and a confirmation is shown

#### Scenario: Set goodbye message template

- GIVEN an admin invokes `/goodbye message Goodbye {user}!`
- WHEN the command executes
- THEN the goodbye message template is saved and cache invalidated

#### Scenario: Non-admin blocked

- GIVEN a non-admin user
- WHEN they invoke `/goodbye config`
- THEN Discord blocks the command (permission hint)
