# Delta for Core Commands

## MODIFIED Requirements

### Requirement: Ping command

The system MUST provide a `ping` command that returns bot latency. Responses MUST be ephemeral.

(Previously: Responses were permanent)

#### Scenario: Latency response

- GIVEN the bot is connected to Discord
- WHEN a user invokes `ping` or `/ping`
- THEN the bot replies ephemerally with a latency value in milliseconds

### Requirement: Status command

The system MUST provide a `status` command that reports system health. Responses MUST be ephemeral. The command MUST be restricted via `@app_commands.default_permissions(moderate_members=True)`.

(Previously: Responses were permanent, no permission restriction)

#### Scenario: Healthy status

- GIVEN all services are healthy
- WHEN a moderator invokes `status` or `/status`
- THEN the bot replies ephemerally with an embed showing database and cache status

#### Scenario: Unhealthy status

- GIVEN the database is unreachable
- WHEN a moderator invokes `status` or `/status`
- THEN the ephemeral embed indicates database failure

#### Scenario: Insufficient permissions

- GIVEN a user without Moderate Members permission
- WHEN they invoke `/status`
- THEN the command is rejected with a permission error
