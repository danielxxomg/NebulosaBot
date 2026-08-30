# Delta for Bot Core

## MODIFIED Requirements

### Requirement: Global error handler

The system MUST handle command errors and respond with user-friendly embeds. Application command errors MUST be sent ephemerally to the invoking user. The handler MUST contain no DM-first branch: with the prefix surface disabled, `on_command_error` retains no prefix-specific delivery logic and MUST NOT attempt DM delivery. The unexpected error embed title and message MUST be resolved via `t()` using the guild's language, not hardcoded English. The handler MUST implement dedicated branches for `CheckFailure` and `MissingPermissions`: each MUST reply ephemerally with a localized, user-friendly message (naming the missing permission when applicable) instead of surfacing an unhandled error. Full tracebacks for these two exception types MUST NOT be shown to users; other unexpected errors keep existing behavior.

(Previously: permission denials surfaced as unhandled errors; this delta adds explicit CheckFailure/MissingPermissions ephemeral branches.)

#### Scenario: Slash command error

- GIVEN a slash command raises an error
- WHEN the error is caught
- THEN an ephemeral embed is sent to the invoking user

#### Scenario: No DM-first branch in prefix handler path

- GIVEN an error surfaces through `on_command_error`
- WHEN the simplified handler processes it
- THEN no DM delivery is attempted (the handler defines no DM-first fallback)

#### Scenario: CheckFailure gets an ephemeral localized reply

- GIVEN a user fails a check on a guarded slash command
- WHEN `CheckFailure` reaches the global handler
- THEN the handler replies ephemerally with a localized denial message (no traceback to the user)

#### Scenario: MissingPermissions names the missing permission

- GIVEN a user lacks a Discord permission required by a command
- WHEN `MissingPermissions` reaches the global handler
- THEN the ephemeral reply states which permission is missing, localized via `t()`

#### Scenario: Unexpected error shows guild language

- GIVEN a Spanish guild
- WHEN an unhandled error occurs in a slash command
- THEN the error embed title and message are in Spanish via `t()`

#### Scenario: Guild resolved from interaction

- GIVEN a slash command error in a guild
- WHEN `on_app_command_error` fires
- THEN `guild_id` is extracted from the interaction to resolve `t()` language

### Requirement: Slash-only command surface

The system MUST expose commands exclusively through Discord slash (application) commands. `get_prefix` MUST resolve to a static empty list (`[]`) — no text prefix enables command invocation. After the S6 migration, ZERO `hybrid_command`/`hybrid_group` declarations MAY remain registered — all surviving commands MUST be pure app commands (`@app_commands.command()` / `app_commands.Group`). `,` (comma) MUST NOT act as a command prefix anywhere in the framework; its sole surviving behavior is the ticket-channel timer listener, which operates outside the command framework and remains specified by `close-confirmation` (unchanged by this delta). Help output MUST display slash syntax only.

(Previously: ~30 legacy hybrid declarations were tolerated as inert; S6 migrates them so none remain.)

#### Scenario: Slash command invocation

- GIVEN the bot is online
- WHEN a user invokes `/ping`
- THEN the bot invokes the `ping` command

#### Scenario: Prefix invocation is inert

- GIVEN a guild with any configuration
- WHEN a user sends `nb!ping`
- THEN no command is invoked and the bot posts no response

#### Scenario: Zero hybrid declarations remain

- GIVEN the fully loaded command tree
- WHEN every registered command's declaration type is inspected
- THEN no command or group is a hybrid declaration; all are pure app commands

#### Scenario: Comma ticket timer is unaffected

- GIVEN a ticket channel governed by `close-confirmation`
- WHEN the `,` timer interaction occurs
- THEN it behaves exactly as specified by `close-confirmation` (unchanged)

#### Scenario: Help shows slash syntax only

- GIVEN the help output is rendered
- WHEN its command entries are inspected
- THEN every entry shows `/command` syntax and none shows a prefix example
