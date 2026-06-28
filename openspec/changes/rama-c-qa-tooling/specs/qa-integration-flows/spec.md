# Integration Flows Specification

## Purpose

Verify end-to-end invariants across cog → service → mocked DB → response for the three highest-risk flows: moderation, tickets, and XP/leveling. These tests prove that the full chain produces correct observable outcomes without requiring a live Discord connection or real database.

## Requirements

### Requirement: Moderation warn round-trip

An integration test MUST verify the full `/warn` flow: command invocation → infraction service → mocked DB insert → log embed content. The test MUST assert that the infraction is persisted and the log embed contains moderator, target, action type, and reason.

#### Scenario: Warn persists infraction and emits log

- GIVEN a moderator with `moderate_members` permission and a target member
- WHEN the moderator issues a `/warn` with a reason
- THEN the mocked DB receives an infraction insert with correct guild, user, action, and reason
- AND a log embed is sent containing the moderator, target, "warn" action type, and the reason

#### Scenario: Warn without log channel skips embed

- GIVEN `logChannelId` is not configured
- WHEN a moderator issues a `/warn`
- THEN the infraction is persisted but no log embed is attempted

### Requirement: Ticket lifecycle round-trip

An integration test MUST verify the ticket lifecycle: panel interaction → channel create → close → transcript generation. The test MUST assert channel creation with correct permissions and transcript file presence on close.

#### Scenario: Open and close ticket

- GIVEN a ticket panel exists with configured category and support role
- WHEN a user clicks the panel button
- THEN a ticket channel is created with the user and support role having access
- WHEN the ticket is closed
- THEN a transcript is generated and the channel is scheduled for deletion

#### Scenario: Ticket channel permissions are correct

- GIVEN a new ticket is opened
- WHEN the channel is created
- THEN the user can send messages and the @everyone role cannot see the channel

### Requirement: XP message-to-level-up flow

An integration test MUST verify that repeated messages accumulate XP and trigger a level-up event when the threshold is crossed. The test MUST assert XP increments and level-up notification delivery.

#### Scenario: Level-up after threshold messages

- GIVEN a member with 0 XP and a configured XP-per-message value
- WHEN the member sends enough messages to cross the level-up threshold
- THEN the member's level increments by 1
- AND a level-up notification is sent to the configured channel

#### Scenario: XP cooldown prevents spam

- GIVEN a member who just gained XP
- WHEN the member sends another message within the cooldown window
- THEN no additional XP is awarded

### Requirement: Mocked dependencies

Integration tests MUST use mocked Discord objects (Member, Interaction, Guild, Channel) and a mocked database layer. Tests MUST NOT make real Discord API calls or connect to a real database.

#### Scenario: No real API calls

- GIVEN integration tests are running
- WHEN any Discord API method is called
- THEN the call is handled by a mock and returns a deterministic fixture
