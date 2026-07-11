# Core Commands Specification

## Purpose

Define the behavior of core utility commands.

## Requirements

### Requirement: Ping command

The system MUST provide a `ping` command that returns bot latency. Responses MUST be ephemeral.

#### Scenario: Latency response

- GIVEN the bot is connected to Discord
- WHEN a user invokes `ping` or `/ping`
- THEN the bot replies ephemerally with a latency value in milliseconds

### Requirement: Status command

The system MUST provide a `status` command that reports system health. Responses MUST be ephemeral. The command MUST be restricted via `@app_commands.default_permissions(moderate_members=True)`.

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

### Requirement: Help command

The system MUST provide a `help` command that returns a custom embed organized by module with pagination. The paginator MUST localize Previous/Next/Stop button labels via `t()` using the invoking guild's language.

(Previously: paginator buttons were hardcoded English "◀ Previous", "Next ▶", "⏹ Stop")

#### Scenario: Help without module

- GIVEN a user invokes `help`
- WHEN no module is specified
- THEN the bot lists available modules

#### Scenario: Help with module

- GIVEN a user invokes `help Sentinel`
- WHEN the module exists
- THEN the bot returns an embed with Sentinel commands and pagination if needed

#### Scenario: Paginator shows Spanish buttons in Spanish guild

- GIVEN a guild with language `es`
- WHEN a user invokes `help` with multiple pages
- THEN the paginator buttons show Spanish labels (e.g., "Anterior", "Siguiente", "Detener")

#### Scenario: Paginator shows English buttons in English guild

- GIVEN a guild with language `en`
- WHEN a user invokes `help` with multiple pages
- THEN the paginator buttons show English labels (e.g., "Previous", "Next", "Stop")

### Requirement: Sync command

The system MUST provide a `sync` command that refreshes slash command registration.

#### Scenario: Sync success

- GIVEN the user has permission
- WHEN `sync` is invoked
- THEN slash commands are updated and a confirmation message is sent
