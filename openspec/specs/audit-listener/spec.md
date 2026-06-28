# Audit Listener Specification

## Purpose

Listen to seven Discord events and route formatted audit data to `LoggingService`.

## Requirements

### Requirement: Event coverage

The system MUST listen to `on_message_edit`, `on_message_delete`, `on_member_join`, `on_member_remove`, `on_member_update`, `on_guild_channel_create`, and `on_guild_channel_delete`.

#### Scenario: All seven events registered

- GIVEN the bot is running
- WHEN any of the seven events fire in a guild
- THEN the corresponding listener invokes `LoggingService`

### Requirement: Early-exit guards

The system MUST skip logging when the guild has no configuration, logging is disabled, or the target channel is invisible to `@everyone`.

#### Scenario: Hidden channel skipped

- GIVEN `@everyone` has `read_messages=False` in the channel
- WHEN a message is edited or deleted there
- THEN no log embed is produced

#### Scenario: Logging disabled skipped

- GIVEN `logEnabled` is false
- WHEN an audit event fires
- THEN no log embed is produced

### Requirement: Message edit logging

The system MUST pass both the original and updated message content to `LoggingService` for `on_message_edit`.

#### Scenario: Edit captured

- GIVEN a message is edited
- WHEN `on_message_edit` fires
- THEN the listener passes the message author, channel, before content, and after content

### Requirement: Message delete logging

The system MUST pass the full deleted message content to `LoggingService` for `on_message_delete`.

#### Scenario: Delete captured

- GIVEN a message is deleted
- WHEN `on_message_delete` fires
- THEN the listener passes the message author, channel, and content

### Requirement: Member and channel events

The system MUST pass member/channel identifiers and relevant state to `LoggingService` for member join, leave, update, and channel create/delete events.

#### Scenario: Member update captured

- GIVEN a member's roles or nickname change
- WHEN `on_member_update` fires
- THEN the listener passes the before and after member objects
