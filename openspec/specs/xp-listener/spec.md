# XP Listener Specification

## Purpose

Define how message activity awards XP, detects level-ups, assigns roles, and sends notifications.

## Requirements

### Requirement: Message XP gain

The system MUST invoke the economy XP gain logic for each valid message and respect the per-user per-guild cooldown.

#### Scenario: Message grants XP

- GIVEN member A sends a message in guild X
- WHEN the cooldown has elapsed
- THEN the economy service awards XP and records the gain time

#### Scenario: Cooldown skips repeated messages

- GIVEN member A sends a second message in guild X within the cooldown window
- WHEN the listener processes the message
- THEN no XP is awarded

#### Scenario: Bot and system messages ignored

- GIVEN the message author is a bot or a system webhook
- WHEN the listener processes the message
- THEN no XP is awarded

### Requirement: Level-up detection

The system MUST compare the member's new level, derived from total XP, with the stored level after each XP gain.

#### Scenario: Level increases

- GIVEN member A has 90 XP at level 1 and the threshold for level 2 is 100 XP
- WHEN a message awards 15 XP
- THEN the stored level updates to 2 and a level-up event is emitted

#### Scenario: No level change

- GIVEN member A has 90 XP at level 1 and the threshold for level 2 is 100 XP
- WHEN a message awards 5 XP
- THEN the stored level remains 1 and no level-up event is emitted

### Requirement: Auto-role assignment

On a level-up, the system MUST assign the role mapped to the new level in `economy_config.levelRoles` if one exists.

#### Scenario: Level role exists

- GIVEN level 5 maps to role R in guild X
- WHEN member A reaches level 5
- THEN role R is added to member A in guild X

#### Scenario: No level role configured

- GIVEN no role is mapped to level 5
- WHEN member A reaches level 5
- THEN no role assignment is attempted

#### Scenario: Higher role already present

- GIVEN member A already has role R mapped to level 5
- WHEN member A reaches level 5
- THEN the role assignment remains idempotent

### Requirement: Level-up notification

On a level-up, the system MUST send an embed notification to the configured level-up channel, or to the current channel if none is configured.

#### Scenario: Configured channel

- GIVEN `levelUpChannelId` is set in guild X
- WHEN member A levels up in guild X
- THEN a level-up embed is sent to that channel

#### Scenario: Fallback channel

- GIVEN `levelUpChannelId` is null in guild X
- WHEN member A levels up in guild X
- THEN a level-up embed is sent to the channel where the message was sent
