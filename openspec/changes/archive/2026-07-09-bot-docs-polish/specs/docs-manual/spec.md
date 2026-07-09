# Delta for Docs Manual

## ADDED Requirements

### Requirement: User manual exists

`docs/MANUAL.md` MUST exist in Spanish and MUST cover all 28 bot commands organized by audience (users, moderators, administrators).

#### Scenario: Manual file present

- GIVEN the repository root
- WHEN inspecting `docs/MANUAL.md`
- THEN the file exists and is non-empty

#### Scenario: Required sections

- GIVEN `docs/MANUAL.md` is read
- WHEN scanning its headings
- THEN it SHALL contain sections for: Quick Start, Configuration, Commands (by audience), Ticket System, Economy, Welcome/Goodbye, and Known Debt

#### Scenario: All commands documented

- GIVEN the 28 commands across 7 cogs
- WHEN reading the manual's command sections
- THEN every command SHALL appear at least once with a brief description
