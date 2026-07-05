# Delta for Ticket Subsidiados

## MODIFIED Requirements

### Requirement: Staff notes

Staff-only (`@is_mod()`) `/note add`, `/note list`, `/note delete`. Notes in `ticket_note`, NOT visible to opener, cap 50/ticket. `/note list` MUST be private: slash = ephemeral; prefix = DM to author + channel confirmation. Note content MUST NOT appear in channel `ctx.send()`.

(Previously: notes sent to shared channel)

#### Scenario: Add note

- GIVEN staff on open ticket
- WHEN `/note add "Customer escalated"`
- THEN row inserted with authorId, content, createdAt

#### Scenario: List notes — slash

- GIVEN ticket with notes
- WHEN staff `/note list` slash
- THEN ephemeral reply with all notes (author + timestamp)

#### Scenario: List notes — prefix

- GIVEN ticket with notes
- WHEN staff `/note list` prefix
- THEN notes DM'd to author, channel gets confirmation-only

#### Scenario: Note content never leaks

- GIVEN any `/note list`
- WHEN handler runs
- THEN channel `ctx.send()` MUST NOT contain note content

#### Scenario: Delete own note

- GIVEN note owned by staffA
- WHEN staffA `/note delete {id}`
- THEN row deleted

#### Scenario: Non-staff rejected

- GIVEN non-mod user
- WHEN `/note add`
- THEN permission error

#### Scenario: Cap enforced

- GIVEN 50 notes on ticket
- WHEN `/note add`
- THEN limit error

### Requirement: Ticket reopen

Staff MAY reopen closed tickets via `/reopen`. MUST reject non-`closed` with error embed showing actual status. On success: new channel, `channelId` updated, `status` → `open`, `closedAt` cleared.

(Previously: no status guard — duplicates on open/claimed)

#### Scenario: Successful reopen

- GIVEN closed ticket #3
- WHEN `/reopen`
- THEN new channel, status → `open`, channelId updated, closedAt = null

#### Scenario: Rejected on open ticket

- GIVEN status `open`
- WHEN `/reopen`
- THEN error embed: "Solo se pueden reabrir tickets cerrados. Estado actual: open"

#### Scenario: Rejected on claimed ticket

- GIVEN status `claimed`
- WHEN `/reopen`
- THEN error embed: "Solo se pueden reabrir tickets cerrados. Estado actual: claimed"

#### Scenario: Category deleted fallback

- GIVEN closed ticket, category deleted
- WHEN `/reopen`
- THEN default category used; if none, error

#### Scenario: Cache updated

- GIVEN ticket reopened
- WHEN new channel created
- THEN `_ticket_channel_cache` updated

### Requirement: Sub-ticket creation

Staff (`@is_mod()`) create child tickets via `/subticket create`. Child: own channel, `parentId`, `ticketNumber`, independent lifecycle. Parent author (parent_owner) MUST get `read_messages`+`send_messages` overwrites and be mentioned. Invoker MUST NOT get extra overwrites — mod role suffices. If invoker IS parent_owner, access already granted.

(Previously: invoker got overwrites; parent_owner got nothing)

#### Scenario: Successful creation

- GIVEN open ticket #5 (id=abc)
- WHEN staff `/subticket create` on #5
- THEN ticket #6 created, parentId=abc, status `open`

#### Scenario: Inherits guild

- GIVEN parent in guild G
- WHEN sub-ticket created
- THEN guildId = G

#### Scenario: Parent owner gets access

- GIVEN parent owned by user U (not invoker)
- WHEN staff `/subticket create`
- THEN U gets read+send overwrites, U mentioned, invoker NO extra overwrites

#### Scenario: Owner creates own sub-ticket

- GIVEN parent owned by user U (staff)
- WHEN U `/subticket create` on own ticket
- THEN U keeps access, is mentioned

#### Scenario: Parent owner offline

- GIVEN parent owner offline
- WHEN `/subticket create`
- THEN overwrite applies

### Requirement: Error handling in new commands

Critical DB calls in subticket, reopen, transfer, note commands MUST NOT surface raw tracebacks. On exception: `error_embed()` + `logging.exception()`.

(Previously: no try/except on critical DB calls)

#### Scenario: get_notes failure

- GIVEN `get_notes()` raises DB exception
- WHEN `/note list`
- THEN `error_embed()`, traceback logged, no raw traceback

#### Scenario: Other critical DB calls

- GIVEN critical DB call raises in any of 4 commands
- WHEN exception occurs
- THEN `error_embed()` + `logging.exception()`

#### Scenario: Non-DB paths excluded

- GIVEN help fallbacks or arg parsing errors
- WHEN they occur
- THEN normal handling (not DB try/except)
