# Docs Manual Specification

## Purpose

Ensure a user-facing Spanish manual exists and covers all bot commands organized by audience.

## Requirements

### Requirement: User manual exists

`docs/MANUAL.md` MUST exist in Spanish and MUST cover all bot commands organized by audience (users, moderators, administrators). The manual MUST document the following ticket UX behaviors: close confirmation dialog (ephemeral Confirm/Cancel), `/unclaim` command (claimer or mods), claim-on-claimed transfer confirmation, channel naming format (`{category}-{username}-{number}`), and brand palette notes (purple/violet embeds, bot avatar footer).

#### Scenario: Manual file present

- GIVEN the repository root
- WHEN inspecting `docs/MANUAL.md`
- THEN the file exists and is non-empty

#### Scenario: Required sections

- GIVEN `docs/MANUAL.md` is read
- WHEN scanning its headings
- THEN it SHALL contain sections for: Quick Start, Configuration, Commands (by audience), Ticket System, Economy, Welcome/Goodbye, and Known Debt

#### Scenario: All commands documented

- GIVEN the commands across all cogs
- WHEN reading the manual's command sections
- THEN every command SHALL appear at least once with a brief description

#### Scenario: Close confirmation documented

- GIVEN the Ticket System section
- WHEN reading about closing tickets
- THEN the manual describes the ephemeral Confirm/Cancel dialog and that dismiss = cancel

#### Scenario: Unclaim command documented

- GIVEN the Ticket System section
- WHEN reading about claim management
- THEN `/unclaim` is documented with its permissions (claimer or mods)

#### Scenario: Claim-on-claimed transfer documented

- GIVEN the Ticket System section
- WHEN reading about claiming tickets
- THEN the manual describes that claiming an already-claimed ticket shows a transfer confirmation

#### Scenario: Channel naming documented

- GIVEN the Ticket System section
- WHEN reading about ticket channels
- THEN the manual describes the `{category}-{username}-{number}` naming format

### Requirement: Dynamic hybrid command discovery test

The system MUST have a test that discovers all `@commands.hybrid_command` decorated functions at runtime and asserts each appears in `docs/MANUAL.md` with a description.

#### Scenario: all hybrid commands appear in manual

- GIVEN all cog modules imported and `@hybrid_command` functions discovered
- WHEN each command name is searched in `docs/MANUAL.md`
- THEN every discovered command name appears at least once

#### Scenario: each command has a description

- GIVEN a hybrid command name found in MANUAL.md
- WHEN the surrounding text is inspected
- THEN a non-empty description line follows the command name

#### Scenario: discovery is resilient to cog load order

- GIVEN cog modules imported in arbitrary order
- WHEN command discovery runs
- THEN the discovered command set is identical regardless of import order
