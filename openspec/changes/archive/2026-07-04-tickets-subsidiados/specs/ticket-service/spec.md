# Delta for Ticket Service

## ADDED Requirements

### Requirement: create_ticket accepts parentId

`create_ticket` MUST accept an optional `parentId` parameter. When set, the service SHALL validate the parentId (exists, not self-ref, not sub-of-sub, same guild) before insert. When set, the "one open ticket per user per category" check MUST be skipped.

#### Scenario: Create with valid parentId

- GIVEN parent ticket (id=abc, guildId=G) exists and is not itself a child
- WHEN `create_ticket(guildId=G, parentId=abc, ...)` is called
- THEN a new ticket is created with `parentId=abc` and no duplicate-check error

#### Scenario: Create without parentId

- GIVEN no parentId argument
- WHEN `create_ticket(guildId=G, ...)` is called
- THEN a ticket is created with `parentId=null` and the one-open-ticket check runs normally

#### Scenario: Invalid parentId raises

- GIVEN parentId references a non-existent ticket
- WHEN `create_ticket(parentId=xyz, ...)` is called
- THEN a `ValueError` MUST be raised before any DB insert

### Requirement: reopen_ticket method

`TicketService.reopen_ticket(ticket_id, guild)` MUST: (1) load the closed ticket, (2) create a new Discord channel with the same category/permissions (fallback to default category if original deleted), (3) update `channelId`, set `status=open`, clear `closedAt`, (4) update `_ticket_channel_cache`.

#### Scenario: Reopen creates new channel

- GIVEN closed ticket #3 (original channel deleted)
- WHEN `reopen_ticket` is called
- THEN a new channel is created and ticket is updated to `open` with new channelId

#### Scenario: Category deleted fallback

- GIVEN closed ticket whose `categoryId` channel no longer exists
- WHEN `reopen_ticket` is called
- THEN the guild's default ticket category is used. If none configured, raise error

#### Scenario: Cache updated

- GIVEN a ticket being reopened
- WHEN the new channel is created
- THEN `_ticket_channel_cache.add(new_channel_id)` is called

### Requirement: transfer_ticket method

`TicketService.transfer_ticket(ticket_id, new_staff_id)` MUST update `claimedBy` and insert an audit log row.

#### Scenario: Transfer updates claimedBy

- GIVEN ticket #4 claimed by userA
- WHEN `transfer_ticket(4, userB)` is called
- THEN `claimedBy` = userB and an audit log row exists

#### Scenario: Transfer unclaimed ticket

- GIVEN ticket with `claimedBy=null`
- WHEN `transfer_ticket` is called
- THEN `claimedBy` is set (implicit claim)

### Requirement: Note CRUD methods

The service MUST provide `create_note(ticket_id, author_id, content)`, `get_notes(ticket_id)`, `delete_note(note_id, author_id)`. Notes are capped at 50 per ticket.

#### Scenario: Create note

- GIVEN a valid ticket
- WHEN `create_note(ticket_id, staff_id, "text")` is called
- THEN a `ticket_note` row is inserted and returned

#### Scenario: Notes cap enforced

- GIVEN ticket has 50 notes
- WHEN `create_note` is called
- THEN `ValueError` is raised with limit message

#### Scenario: Delete own note

- GIVEN note owned by staffA
- WHEN `delete_note(note_id, staffA)` is called
- THEN the row is deleted

#### Scenario: Delete other's note rejected

- GIVEN note owned by staffA
- WHEN `delete_note(note_id, staffB)` is called
- THEN a `ValueError` is raised
