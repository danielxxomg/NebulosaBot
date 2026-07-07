# Delta for Bot Core

## MODIFIED Requirements

### Requirement: Hybrid prefix

The system MUST support both slash commands and prefix commands, using a configurable prefix that defaults to `nb!`. The system MUST also accept `,` (comma) as a global alternate prefix for all prefix commands.

(Previously: Only supported configurable prefix, no alternate prefix)

#### Scenario: Prefix command invocation

- GIVEN a guild with default configuration
- WHEN a user sends `nb!ping`
- THEN the bot invokes the `ping` command

#### Scenario: Alternate prefix invocation

- GIVEN the bot is online
- WHEN a user sends `,ping`
- THEN the bot invokes the `ping` command

#### Scenario: Slash command invocation

- GIVEN the bot is online
- WHEN a user invokes `/ping`
- THEN the bot invokes the `ping` command

### Requirement: Global error handler

The system MUST handle command errors and respond with user-friendly embeds. Slash command errors MUST be sent ephemerally. Prefix command errors MUST be sent as a DM to the invoking user; if the DM fails, the error is sent to the channel.

(Previously: Prefix errors were sent to the channel)

#### Scenario: Slash command error

- GIVEN a slash command raises an error
- WHEN the error is caught
- THEN an ephemeral embed is sent to the invoking user

#### Scenario: Prefix command error DM

- GIVEN a prefix command raises an error
- WHEN the error is caught
- THEN an embed is sent as a DM to the invoking user

#### Scenario: Prefix error DM failure

- GIVEN a prefix command raises an error
- WHEN the bot cannot DM the user
- THEN the embed is sent to the channel where the command was invoked

## ADDED Requirements

### Requirement: Alternate comma prefix

The system MUST recognize `,` (comma) as a hardcoded global alternate prefix in addition to the guild-configured prefix.

#### Scenario: Comma prefix works

- GIVEN a guild with prefix `nb!`
- WHEN a user sends `,ping`
- THEN the bot responds as if `nb!ping` was sent

#### Scenario: Comma prefix with arguments

- GIVEN a guild with prefix `nb!`
- WHEN a user sends `,warn @user spam`
- THEN the `warn` command is invoked with arguments `@user spam`
