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

<!-- BEGIN DELTA: product-artifact-audit (audit-listener) -->
## ADDED Requirements

### Requirement: Authoritative channel-delete routing

`on_guild_channel_delete` MUST preserve the existing channel audit log and route active-ticket detection to the Ticket Service shared repair path. The listener MUST provide guild and channel facts for per-ticket corroboration, but MUST NOT mutate tickets independently. An audit-log actor, when available, is informational only and MUST NOT decide integrity, authorization, or repair.

#### Scenario: Deleted ticket channel is routed

- GIVEN an active ticket maps to the deleted channel
- WHEN `on_guild_channel_delete` fires
- THEN the shared service path receives the event and no parallel mutation occurs

#### Scenario: Non-ticket deletion preserves behavior

- GIVEN no active ticket maps to the deleted channel
- WHEN the event fires
- THEN normal deletion logging continues and no repair result is claimed

#### Scenario: Actor attribution cannot authorize repair

- GIVEN the Discord audit event identifies an actor who deleted the channel
- WHEN repair eligibility is evaluated
- THEN the actor is recorded as context only and cannot make unsafe evidence actionable

### Requirement: Shared entry-point delegation

Startup sweeps, periodic sweeps, and manual fallback triggers MUST delegate candidate evaluation to the same Ticket Service repair path. The listener MUST honor its bounded batch and backoff result, and MUST surface transient or ambiguous outcomes for review instead of retrying with an independent mutation path.

#### Scenario: Duplicate delete events converge

- GIVEN duplicate delete events arrive for one ticket
- WHEN both are dispatched
- THEN the shared path yields one transition and one deterministic no-op outcome

#### Scenario: Transient Discord failure is deferred

- GIVEN a per-ticket channel check raises a timeout or rate-limit error
- WHEN the event or sweep is processed
- THEN the candidate is reported/quarantined and no ticket mutation occurs

#### Scenario: Preflight is stale

- GIVEN schema/deployment preflight is stale while a deleted ticket channel is detected
- WHEN the listener dispatches the candidate
- THEN detection and reporting occur, but automatic repair is not attempted

<!-- END DELTA: product-artifact-audit (audit-listener) -->
