# Logging Service Specification

## Purpose

Centralize log embed formatting and routing to the configured log channel.

## Requirements

### Requirement: Typed log methods

The system MUST expose typed methods on `LoggingService` for moderation actions, message edits, message deletes, member join/leave/update, and channel create/delete.

#### Scenario: Moderation action log

- GIVEN `logEnabled` is true and `logChannelId` is set
- WHEN `LoggingService.log_moderation_action()` is called
- THEN a formatted embed is sent to the log channel

### Requirement: Embed routing

The system MUST send log embeds to `logChannelId` and skip silently when the channel is null or logging is disabled.

#### Scenario: Missing channel

- GIVEN `logChannelId` is null
- WHEN any log method is called
- THEN no embed is sent and no error is surfaced

#### Scenario: Logging disabled

- GIVEN `logEnabled` is false
- WHEN any log method is called
- THEN no embed is sent

### Requirement: Content detail

The system MUST include before and after content for message edits and full content for message deletes.

#### Scenario: Edit log detail

- GIVEN a message edit event is logged
- THEN the embed contains the original content and the updated content

#### Scenario: Delete log detail

- GIVEN a message delete event is logged
- THEN the embed contains the deleted message content

### Requirement: Channel visibility filter

The system MUST skip logging events that occur in channels where `@everyone` has `read_messages=False`.

#### Scenario: Private channel event

- GIVEN a message is deleted in a channel invisible to `@everyone`
- WHEN `LoggingService.log_message_delete()` is called
- THEN no embed is sent
