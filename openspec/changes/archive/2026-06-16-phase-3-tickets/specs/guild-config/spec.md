# Delta for Guild Configuration

## ADDED Requirements

### Requirement: Panel persistence fields

The system MUST store the deployed ticket panel message ID and channel ID in the guild configuration.

#### Scenario: Panel deployment persisted

- GIVEN `/ticket_panel` deploys a panel message
- WHEN the deployment succeeds
- THEN `ticketPanelMessageId` and `ticketPanelChannelId` are updated in the guild record and cache

#### Scenario: Panel lookup on startup

- GIVEN a guild has stored panel IDs
- WHEN the bot starts
- THEN the panel message is located and the persistent view is re-registered

#### Scenario: Missing panel message

- GIVEN stored panel IDs point to a deleted message
- WHEN the bot starts
- THEN the stale IDs are cleared and a warning is logged
