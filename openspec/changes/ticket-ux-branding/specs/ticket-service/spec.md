# Delta for Ticket Service

## ADDED Requirements

### Requirement: Unclaim ticket method

`TicketService.unclaim_ticket(ticket_id)` MUST set `claimedBy=null` and `status='open'`. The method SHALL validate that the ticket is currently claimed before proceeding. On success, an audit row with action=unclaim MUST be written.

#### Scenario: Unclaim a claimed ticket

- GIVEN ticket #5 claimed by userA with status `claimed`
- WHEN `unclaim_ticket(5)` is called
- THEN `claimedBy=null`, `status='open'`, and audit row is written

#### Scenario: Unclaim unclaimed ticket rejected

- GIVEN ticket #6 with `claimedBy=null` and status `open`
- WHEN `unclaim_ticket(6)` is called
- THEN `ValueError` is raised (ticket is not claimed)

### Requirement: Close countdown flow

After manual close confirmation, `close_ticket_full()` MUST post ONE message to the channel and edit it counting from 5 to 1 (one edit per second), then delete the channel. The `CHANNEL_DELETE_DELAY` silent sleep MUST be replaced by this countdown for manual close only.

#### Scenario: Countdown replaces silent delay

- GIVEN a manually confirmed ticket close
- WHEN `close_ticket_full()` executes
- THEN ONE message is posted and edited 5→4→3→2→1, then the channel is deleted

#### Scenario: Auto-close uses silent delete

- GIVEN the auto-close task for a 48h stale ticket
- WHEN `close_ticket_full()` is called from auto-close context
- THEN the channel is deleted silently without countdown messages

### Requirement: Channel naming in service

`create_ticket_channel()` and `reopen_ticket()` MUST use `sanitize_channel_name()` from `ticket_helpers.py` to generate channel names in `{category}-{username}-{number}` format.

#### Scenario: create_ticket_channel uses new naming

- GIVEN a ticket creation request with category "Soporte" and user "Daniel"
- WHEN `create_ticket_channel()` is called
- THEN the channel name is generated via `sanitize_channel_name("Soporte", "Daniel", number)`

#### Scenario: reopen_ticket uses new naming

- GIVEN ticket #42 being reopened
- WHEN `reopen_ticket()` creates a new channel
- THEN the channel name uses `sanitize_channel_name()` with the original category and username

## MODIFIED Requirements

### Requirement: Ticket creation

The system MUST create a new ticket channel with a sequential ticket number per guild. `create_ticket()` SHALL accept optional `subject: str | None`, `description: str | None`, and `custom_fields: dict | None` parameters and persist them to the database. Channel names MUST use `sanitize_channel_name()` format (`{category}-{username}-{number}`).

(Previously: channel names used `ticket-{number:04d}` format)

#### Scenario: Successful creation

- GIVEN a guild with ticket category configured
- WHEN a user opens a ticket
- THEN a channel is created with `sanitize_channel_name()` format and a Ticket row is inserted with status `open`

#### Scenario: Sequential numbering

- GIVEN the highest existing ticket number in the guild is 12
- WHEN a new ticket is created
- THEN the new ticket number is 13

#### Scenario: Race condition retry

- GIVEN two tickets are created simultaneously and both read ticket number 13
- WHEN the first insert succeeds
- THEN the second attempt MUST retry with ticket number 14 within 3 attempts

#### Scenario: Creation with subject and description

- GIVEN subject="Login broken" and description="Cannot access since Monday"
- WHEN `create_ticket(subject=..., description=...)` is called
- THEN the Ticket row includes subject="Login broken" and description="Cannot access since Monday"

#### Scenario: Creation without subject and description

- GIVEN no subject or description arguments
- WHEN `create_ticket()` is called
- THEN the Ticket row has subject=null and description=null

#### Scenario: Creation with custom_fields

- GIVEN `custom_fields = {"player_nick": "DarkSlayer42", "evidence_url": "https://imgur.com/..."}`
- WHEN `create_ticket(custom_fields=...)` is called
- THEN the Ticket row includes `customFields` with the provided dict

#### Scenario: Creation without custom_fields

- GIVEN no custom_fields argument
- WHEN `create_ticket()` is called
- THEN the Ticket row has `customFields = {}`

### Requirement: Ticket close

The system MUST close a ticket, generate a transcript, and delete the channel. Manual close MUST use a countdown (5→1 edited message) before channel deletion. Auto-close MUST delete silently.

(Previously: all closes used silent 5-second delay)

#### Scenario: Close with transcript

- GIVEN an open ticket with messages
- WHEN the close action is triggered
- THEN a transcript is generated, uploaded to the log channel, the Ticket row status becomes `closed`, and the channel is deleted after countdown

#### Scenario: Close unclaimed ticket

- GIVEN an unclaimed open ticket
- WHEN close is triggered
- THEN the ticket is closed normally and `claimedBy` remains null
