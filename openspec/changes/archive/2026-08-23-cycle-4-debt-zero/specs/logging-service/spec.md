# Delta for Logging Service

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
