# Delta for Docs Manual

## MODIFIED Requirements

### Requirement: User manual exists

`docs/MANUAL.md` MUST exist in Spanish and MUST cover all bot commands organized by audience (users, moderators, administrators). The manual MUST document the following ticket UX behaviors: close confirmation dialog (ephemeral Confirm/Cancel), `/unclaim` command (claimer or mods), claim-on-claimed transfer confirmation, channel naming format (`{category}-{username}-{number}`), and brand palette notes (purple/violet embeds, bot avatar footer).

(Previously: manual existed but did not cover close confirmation, unclaim, transfer-on-claim, or channel naming)

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
