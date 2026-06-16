# Infraction Service Specification

## Purpose

Centralize creation, retrieval, update, and deletion of moderation infractions, keep the denormalized `Member.warnings` counter in sync, and apply automatic escalation when warning thresholds are reached.

## Requirements

### Requirement: Create infraction

The system MUST create an `Infraction` record and increment `Member.warnings` when a warning is issued.

#### Scenario: Warn user

- GIVEN a guild member has 0 warnings
- WHEN a moderator issues a WARN infraction
- THEN the infraction is persisted and the member's warning count becomes 1

### Requirement: Read infractions

The system MUST retrieve infractions scoped to a guild and target user, optionally filtered by type and active status.

#### Scenario: List active warnings

- GIVEN a member has 2 active WARN infractions in a guild
- WHEN the service queries active warnings for that member
- THEN it returns exactly those 2 infractions

### Requirement: Update infraction

The system MUST allow a moderator to update an existing infraction's reason and active state.

#### Scenario: Edit reason

- GIVEN an active WARN infraction exists
- WHEN a moderator updates its reason to "updated reason"
- THEN the persisted reason is changed and active remains true

### Requirement: Delete infraction

The system MUST allow authorized moderators to delete an infraction and decrement the member's warning count.

#### Scenario: Delete warning

- GIVEN a member has 2 warnings and an infraction exists
- WHEN the infraction is deleted
- THEN the infraction is removed and the warning count becomes 1

### Requirement: Auto-escalation at 3 warnings

The system MUST automatically apply a 1-hour mute when a member's warning count reaches 3.

#### Scenario: Third warning triggers mute

- GIVEN a member has 2 warnings
- WHEN a moderator issues the third WARN infraction
- THEN a 1-hour MUTE infraction is created and the member is muted for 1 hour

### Requirement: Auto-escalation at 5 warnings

The system MUST automatically kick the member when the warning count reaches 5.

#### Scenario: Fifth warning triggers kick

- GIVEN a member has 4 warnings
- WHEN a moderator issues the fifth WARN infraction
- THEN a KICK infraction is created and the member is removed from the guild

### Requirement: Escalation notification

The system SHOULD notify the target user and the channel when an escalation action is taken.

#### Scenario: Notify on auto-mute

- GIVEN a member reaches 3 warnings
- WHEN the auto-escalation mute is applied
- THEN the member receives a DM and a public message is sent in the channel
