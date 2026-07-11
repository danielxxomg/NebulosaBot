# Bot Core Specification

## Purpose

Define the behavior of the bot instance, lifecycle hooks, command prefix resolution, cog loading, and global error handling.

## Requirements

### Requirement: Bot lifecycle

The system MUST initialize the bot instance and execute a setup hook before connecting to Discord.

#### Scenario: Startup

- GIVEN the bot process starts
- WHEN `setup_hook` runs
- THEN cogs are loaded and services are ready before the connection to Discord is established

### Requirement: Hybrid prefix

The system MUST support both slash commands and prefix commands, using a configurable prefix that defaults to `nb!`. The system MUST also accept `,` (comma) as a global alternate prefix for all prefix commands.

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

### Requirement: Cog loading

The system MUST load command modules (cogs) during `setup_hook`.

#### Scenario: Cog discovery

- GIVEN valid cogs exist in the cogs directory
- WHEN `setup_hook` executes
- THEN every valid cog is loaded and its commands are registered

#### Scenario: Cog load failure

- GIVEN a cog contains an error
- WHEN `setup_hook` attempts to load it
- THEN the bot logs the error and continues loading the remaining cogs

### Requirement: Global error handler

The system MUST handle command errors and respond with user-friendly embeds. Slash command errors MUST be sent ephemerally. Prefix command errors MUST be sent as a DM to the invoking user; if the DM fails, the error is sent to the channel. The unexpected error embed title and message MUST be resolved via `t()` using the guild's language, not hardcoded English.

(Previously: `on_app_command_error` used hardcoded `error_embed("Unexpected Error", ...)`)

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

#### Scenario: Unexpected error shows guild language

- GIVEN a Spanish guild
- WHEN an unhandled error occurs in a slash command
- THEN the error embed title and message are in Spanish via `t()`

#### Scenario: Unexpected error in English guild

- GIVEN an English guild
- WHEN an unhandled error occurs in a slash command
- THEN the error embed title and message are in English via `t()`

#### Scenario: Guild resolved from interaction

- GIVEN a slash command error in a guild
- WHEN `on_app_command_error` fires
- THEN `guild_id` is extracted from the interaction to resolve `t()` language

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
