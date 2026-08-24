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

### Requirement: Slash-only command surface

The system MUST expose commands exclusively through Discord slash (application) commands. `get_prefix` MUST resolve to a static empty list (`[]`) — no text prefix enables command invocation. Zero text-invocable commands MUST remain registered. `,` (comma) MUST NOT act as a command prefix anywhere in the framework; its sole surviving behavior is the ticket-channel timer listener, which operates outside the command framework and remains specified by `close-confirmation` (unchanged by this delta). Help output MUST display slash syntax only.

#### Scenario: Slash command invocation

- GIVEN the bot is online
- WHEN a user invokes `/ping`
- THEN the bot invokes the `ping` command

#### Scenario: Prefix invocation is inert

- GIVEN a guild with any configuration
- WHEN a user sends `nb!ping`
- THEN no command is invoked and the bot posts no response

#### Scenario: Comma invocation is inert outside ticket channels

- GIVEN the bot is online
- WHEN a user sends `,ping` in a non-ticket channel
- THEN no command is invoked and the bot posts no response

#### Scenario: Comma ticket timer is unaffected

- GIVEN a ticket channel governed by `close-confirmation`
- WHEN the `,` timer interaction occurs
- THEN it behaves exactly as specified by `close-confirmation` (unchanged)

#### Scenario: Help shows slash syntax only

- GIVEN the help output is rendered
- WHEN its command entries are inspected
- THEN every entry shows `/command` syntax and none shows a prefix example

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

The system MUST handle command errors and respond with user-friendly embeds. Application command errors MUST be sent ephemerally to the invoking user. The handler MUST contain no DM-first branch: with the prefix surface disabled, `on_command_error` retains no prefix-specific delivery logic and MUST NOT attempt DM delivery. The unexpected error embed title and message MUST be resolved via `t()` using the guild's language, not hardcoded English.

#### Scenario: Slash command error

- GIVEN a slash command raises an error
- WHEN the error is caught
- THEN an ephemeral embed is sent to the invoking user

#### Scenario: No DM-first branch in prefix handler path

- GIVEN an error surfaces through `on_command_error`
- WHEN the simplified handler processes it
- THEN no DM delivery is attempted (the handler defines no DM-first fallback)

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
