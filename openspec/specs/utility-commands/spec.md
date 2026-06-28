# Utility Commands Specification

## Purpose

Provide guild members with quick, read-only information about users and the current server via hybrid commands.

## Requirements

### Requirement: Avatar command

The `/avatar` command MUST display the target user's avatar as a thumbnail embed.

#### Scenario: Self avatar

- GIVEN a member invokes `/avatar` without a target
- WHEN the command executes
- THEN the bot SHALL reply with an embed whose thumbnail is the invoking member's avatar URL

#### Scenario: Mentioned member avatar

- GIVEN a member invokes `/avatar @member`
- WHEN the command executes
- THEN the bot SHALL reply with an embed whose thumbnail is the mentioned member's avatar URL

### Requirement: Server info command

The `/serverinfo` command MUST return a guild summary embed containing name, owner, member count, channel count, role count, and creation date.

#### Scenario: Guild context

- GIVEN the command is invoked inside a guild
- WHEN the command executes
- THEN the bot SHALL reply with an embed showing the guild's name, owner mention, total members, channel count, role count, and creation timestamp

#### Scenario: DM context

- GIVEN the command is invoked in a DM channel
- WHEN the command executes
- THEN the bot SHALL reply with an error embed stating the command only works in servers

### Requirement: User info command

The `/userinfo` command MUST return a member summary embed with name, ID, roles, join date, and account creation date.

#### Scenario: Member with few roles

- GIVEN a member invokes `/userinfo` on a member with 20 or fewer roles
- WHEN the command executes
- THEN the bot SHALL reply with an embed listing all roles, plus join date and account creation date

#### Scenario: Member with many roles

- GIVEN a member invokes `/userinfo` on a member with more than 20 roles
- WHEN the command executes
- THEN the bot SHALL reply with an embed listing the first 20 roles followed by "and N more"
