# Delta for bot-core

## MODIFIED Requirements

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
