# Core Commands Specification

## Purpose

Define the behavior of core utility commands.

## Requirements

### Requirement: Ping command

The system MUST provide a `ping` command that returns bot latency.

#### Scenario: Latency response

- GIVEN the bot is connected to Discord
- WHEN a user invokes `ping`
- THEN the bot replies with a latency value in milliseconds

### Requirement: Status command

The system MUST provide a `status` command that reports system health.

#### Scenario: Healthy status

- GIVEN all services are healthy
- WHEN a user invokes `status`
- THEN the bot replies with an embed showing database and cache status

#### Scenario: Unhealthy status

- GIVEN the database is unreachable
- WHEN a user invokes `status`
- THEN the embed indicates database failure

### Requirement: Help command

The system MUST provide a `help` command that returns a custom embed organized by module with pagination.

#### Scenario: Help without module

- GIVEN a user invokes `help`
- WHEN no module is specified
- THEN the bot lists available modules

#### Scenario: Help with module

- GIVEN a user invokes `help Sentinel`
- WHEN the module exists
- THEN the bot returns an embed with Sentinel commands and pagination if needed

### Requirement: Sync command

The system MUST provide a `sync` command that refreshes slash command registration.

#### Scenario: Sync success

- GIVEN the user has permission
- WHEN `sync` is invoked
- THEN slash commands are updated and a confirmation message is sent
