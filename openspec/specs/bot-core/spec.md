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

The system MUST support both slash commands and prefix commands, using a configurable prefix that defaults to `nb!`.

#### Scenario: Prefix command invocation

- GIVEN a guild with default configuration
- WHEN a user sends `nb!ping`
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

The system MUST handle command errors and respond with user-friendly embeds.

#### Scenario: Slash command error

- GIVEN a slash command raises an error
- WHEN the error is caught
- THEN an ephemeral embed is sent to the invoking user

#### Scenario: Prefix command error

- GIVEN a prefix command raises an error
- WHEN the error is caught
- THEN an embed is sent to the channel where the command was invoked
