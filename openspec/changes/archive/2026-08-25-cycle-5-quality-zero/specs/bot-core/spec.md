# Delta for bot-core

> Change: `cycle-5-quality-zero`. Scope: hybrid/comma prefix requirements reduced to slash-only; `,` survives solely as the ticket-channel timer (governed by `close-confirmation`, explicitly UNCHANGED here).

## RENAMED Requirements

### Requirement: Hybrid prefix → Slash-only command surface

(Reason: the approved slash-only decision replaces the hybrid command surface; the requirement now describes slash registration plus an inert prefix resolver.)
(Migration: rename in tests/docs; scenarios asserting `nb!`/`,` command invocation are replaced by inertness assertions.)

## MODIFIED Requirements

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

### Requirement: Global error handler

The system MUST handle command errors and respond with user-friendly embeds. Application command errors MUST be sent ephemerally to the invoking user. The handler MUST contain no DM-first branch: with the prefix surface disabled, `on_command_error` retains no prefix-specific delivery logic and MUST NOT attempt DM delivery. The unexpected error embed title and message MUST be resolved via `t()` using the guild's language, not hardcoded English.

(Previously: prefix command errors were delivered DM-first with a channel fallback.)
(Previously: `on_app_command_error` used hardcoded `error_embed("Unexpected Error", ...)`)

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

## REMOVED Requirements

### Requirement: Alternate comma prefix

(Reason: `,` as a global alternate command prefix contradicts the approved slash-only decision; zero text-invocable commands must remain.)
(Migration: `,` behavior continues solely as the ticket-channel timer defined in `close-confirmation`, which is unchanged; tests asserting `,ping`/`,warn` invocation are deleted or replaced by inertness assertions in "Slash-only command surface".)
