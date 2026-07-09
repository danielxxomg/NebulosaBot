# Delta for Ticket Service

## MODIFIED Requirements

### Requirement: Ticket creation

The system MUST create a new ticket channel with a sequential ticket number per guild. `create_ticket()` SHALL accept optional `subject: str | None` and `description: str | None` parameters and persist them to the database.

(Previously: create_ticket did not accept subject/description)

#### Scenario: Successful creation

- GIVEN a guild with ticket category configured
- WHEN a user opens a ticket
- THEN a channel is created under the ticket category and a Ticket row is inserted with status `open`

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

### Requirement: Channel creation extracted to service

`create_ticket_channel()` SHALL accept optional `subject: str | None` and `description: str | None` parameters and pass them through to `create_ticket()`. This supports both the modal intake flow (with subject/description) and the sub-ticket flow (without them).

(Previously: create_ticket_channel did not accept subject/description)

#### Scenario: create_ticket_channel called

- GIVEN guild config, author, category_id, and mod_role
- WHEN `TicketService.create_ticket_channel()` is called
- THEN a Discord channel is created with correct overwrites and a Ticket row is inserted

#### Scenario: create_ticket_channel with subject and description

- GIVEN subject and description from modal intake
- WHEN `TicketService.create_ticket_channel(subject=..., description=...)` is called
- THEN the values are passed through to `create_ticket()`

#### Scenario: create_ticket_channel without subject and description

- GIVEN no subject or description (sub-ticket flow)
- WHEN `TicketService.create_ticket_channel()` is called
- THEN `create_ticket()` is called with subject=None and description=None
