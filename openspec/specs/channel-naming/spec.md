# Channel Naming Specification

## Purpose

Descriptive ticket channel names using `{category}-{username}-{number}` format for all creation and rename paths.

## Requirements

### Requirement: Channel name format

Ticket channel names MUST follow the pattern `{category_slug}-{username}-{ticket_number}`, sanitized to lowercase alphanumeric with hyphens, truncated to 100 characters maximum.

#### Scenario: Standard channel name

- GIVEN a ticket in category "Soporte" opened by user "DanielXX" with ticket number 42
- WHEN the ticket channel is created
- THEN the channel name is `soporte-danielxx-0042`

#### Scenario: Long name truncated

- GIVEN a ticket with a combined name exceeding 100 characters
- WHEN the channel is created
- THEN the name is truncated to 100 characters while preserving the ticket number suffix

#### Scenario: Special characters sanitized

- GIVEN a category name "Soporte Técnico" and username "user_123!"
- WHEN the channel name is generated
- THEN special characters are stripped and spaces become hyphens: `soporte-tecnico-user123-0042`

### Requirement: Naming applied to all paths

The `{category}-{username}-{number}` naming MUST be applied to: initial ticket creation, reopen, subtickets, and post-create rename.

#### Scenario: Reopen uses new naming

- GIVEN ticket #42 reopened from closed state
- WHEN a new channel is created
- THEN the channel name uses the new `{category}-{username}-{number}` format

#### Scenario: Subticket uses new naming

- GIVEN a subticket created under an existing ticket
- WHEN the subticket channel is created
- THEN the channel name uses the new naming format with the subticket's number

#### Scenario: Post-create rename

- GIVEN a ticket created with a tentative number that differs from the actual number
- WHEN the rename occurs
- THEN the channel is renamed to the correct `{category}-{username}-{number}` format

### Requirement: sanitize_channel_name helper

A `sanitize_channel_name()` helper MUST exist in `bot/utils/ticket_helpers.py` that accepts category name, username, and ticket number, and returns a sanitized channel name.

#### Scenario: Helper returns valid name

- GIVEN category="Soporte", username="DanielXX", number=42
- WHEN `sanitize_channel_name("Soporte", "DanielXX", 42)` is called
- THEN the result is `soporte-danielxx-0042`

#### Scenario: Helper handles empty inputs

- GIVEN category="" or username=""
- WHEN `sanitize_channel_name()` is called
- THEN the function handles empty inputs gracefully with fallback defaults
