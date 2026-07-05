# Delta for Ticket Service

## MODIFIED Requirements

### Requirement: reopen_ticket method

`TicketService.reopen_ticket(ticket_id, guild)` MUST reject calls when the ticket status is not `closed` by raising `ValueError`. When status is `closed`, the service SHALL: (1) load the closed ticket, (2) create a new Discord channel with the same category/permissions (fallback to default category if original deleted), (3) update `channelId`, set `status=open`, clear `closedAt`, (4) update `_ticket_channel_cache`.

(Previously: no status guard — `reopen_ticket` proceeded on any status, creating duplicate channels for open/claimed tickets)

#### Scenario: Reopen creates new channel

- GIVEN closed ticket #3 (original channel deleted)
- WHEN `reopen_ticket` is called
- THEN a new channel is created and ticket is updated to `open` with new channelId

#### Scenario: Reopen rejected on non-closed ticket

- GIVEN ticket #4 with status `open` or `claimed`
- WHEN `reopen_ticket(4, guild)` is called
- THEN `ValueError` is raised (defense-in-depth; cog layer sends error embed to user)

#### Scenario: Category deleted fallback

- GIVEN closed ticket whose `categoryId` channel no longer exists
- WHEN `reopen_ticket` is called
- THEN the guild's default ticket category is used. If none configured, raise error

#### Scenario: Cache updated

- GIVEN a ticket being reopened
- WHEN the new channel is created
- THEN `_ticket_channel_cache.add(new_channel_id)` is called
