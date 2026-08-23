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

<!-- BEGIN DELTA: product-artifact-audit (logging-service) -->
## ADDED Requirements

### Requirement: Separate guild audit from systemic diagnosis

The logging service MUST distinguish per-guild ticket audit from bot-operator systemic diagnosis. Guild audit output MUST be guild-scoped. Operator diagnosis MAY aggregate across guilds, but it MUST identify target guilds and MUST NOT imply mutation authority. Any operator mutation outcome MUST remain explicit and auditable through the service and invariant contracts.

#### Scenario: Guild admin sees only guild evidence

- GIVEN audit evidence exists for guilds A and B
- WHEN a guild A audit view is produced
- THEN only guild A evidence is returned

#### Scenario: Operator diagnosis is global but read-only

- GIVEN an operator requests a cross-guild integrity report without mutation authority
- WHEN diagnosis is generated
- THEN global findings may be reported, but no ticket mutation is claimed

### Requirement: Reviewable repair outcome logging

Every denied, quarantined, skipped, transient-error, and already-closed repair outcome MUST produce structured, non-empty evidence including ticket, guild, outcome, reason, and source when available. Successful mutation MUST be distinguishable from no-op/quarantine. A channel-delete actor MUST be labeled informational context only and MUST NOT be logged as the authorization decision.

#### Scenario: Denied operation has evidence

- GIVEN a permission or preflight gate denies repair
- WHEN the result is logged
- THEN the record contains a non-empty reason and does not report mutation

#### Scenario: Quarantine is visibly non-mutating

- GIVEN evidence is missing, ambiguous, or stale
- WHEN the report is emitted
- THEN it is marked review/quarantine or no-op, never repaired/success

#### Scenario: Duplicate event is not double-counted

- GIVEN the same deletion event is delivered twice
- WHEN both results are logged
- THEN one success at most is recorded and the loser is a deterministic no-op/denied outcome

### Requirement: Resilient diagnostic delivery

Transient Discord, database, or audit-write failures MUST be logged with their retryable classification and MUST NOT be converted into successful repair evidence. Logging failure MUST NOT turn a quarantine/no-op into a mutation claim; the service MUST retain enough structured context for later review.

#### Scenario: Retryable failure is reportable

- GIVEN a sweep receives a timeout or rate-limit response
- WHEN logging handles the failure
- THEN the report records the transient reason and candidate remains unmutated

<!-- END DELTA: product-artifact-audit (logging-service) -->

<!-- BEGIN DELTA: cycle-4-debt-zero (logging-service) -->
## ADDED Requirements

### Requirement: Zero-count digest suppression

Digest-style log embeds driven by periodic loops (scheduled-close scans, sentinel hourly loop) MUST be sent to the log channel only when the summarized event count is greater than zero; a zero-count cycle MUST produce no embed. Routine per-cycle progress messages in those loops (e.g. "checking due tickets" each cycle) MUST be logged at DEBUG level, not INFO.

#### Scenario: Zero due tickets emit nothing

- GIVEN a scheduled-close scan finds zero due tickets
- WHEN the cycle completes
- THEN no digest embed is sent and the cycle's progress line appears only at DEBUG

#### Scenario: Nonzero digest still delivers

- GIVEN a scan or hourly loop summarizes one or more events
- WHEN the cycle completes
- THEN the digest embed is sent to the configured log channel as before

### Requirement: Global error handlers log exceptions

The global command error handlers (`on_app_command_error` for slash, `on_command_error` for prefix) MUST log the full exception with traceback BEFORE any user-facing response is produced. Discarding the error parameter, or responding to the user without logging, MUST NOT occur.

#### Scenario: Slash command error logged

- GIVEN an application command raises an unhandled exception
- WHEN `on_app_command_error` handles it
- THEN the full exception is logged with traceback and the user still receives the standard error embed

#### Scenario: Prefix command error logged

- GIVEN a prefix command raises an unhandled exception
- WHEN `on_command_error` handles it
- THEN the full exception is logged with traceback and no raw traceback reaches the user
<!-- END DELTA: cycle-4-debt-zero (logging-service) -->
