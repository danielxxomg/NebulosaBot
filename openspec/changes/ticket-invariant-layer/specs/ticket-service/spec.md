# Delta for Ticket Service

## MODIFIED Requirements

### Requirement: transfer_ticket method

`TicketService.transfer_ticket(ticket_id, new_staff_id)` MUST update `claimedBy`, set `status='claimed'`, and insert an audit log row.

(Previously: transfer only set `claimedBy`, did not normalize `status`)

#### Scenario: Transfer updates claimedBy and status

- GIVEN ticket #4 claimed by userA with status `claimed`
- WHEN `transfer_ticket(4, userB)` is called
- THEN `claimedBy` = userB, `status` = `claimed`, and an audit log row exists

#### Scenario: Transfer unclaimed ticket sets status

- GIVEN ticket with `claimedBy=null` and status `open`
- WHEN `transfer_ticket` is called
- THEN `claimedBy` is set and `status` becomes `claimed`

### Requirement: Ticket claim

The system MUST allow staff to claim an open ticket. Claim on an already-claimed ticket MUST be rejected — reassignment SHALL use `transfer_ticket`.

(Previously: scenario described rejection but requirement text did not mandate no-overwrite explicitly)

#### Scenario: Staff claims ticket

- GIVEN an open ticket
- WHEN a staff member clicks the claim button
- THEN the ticket status becomes `claimed` and `claimedBy` is set to the staff user ID

#### Scenario: Already claimed rejected

- GIVEN a ticket already claimed by another staff member
- WHEN a staff member clicks claim
- THEN the action is rejected and the existing claim is preserved

#### Scenario: Same-user re-claim rejected

- GIVEN a ticket claimed by userA
- WHEN userA clicks claim again
- THEN the action is rejected

## ADDED Requirements

### Requirement: Note dedup enforcement

The service MUST reject duplicate notes. Dedup hash = SHA256 of `trim(content).lower().collapse_whitespace()`. Compared against notes from same `authorId` within a 2-second window. On duplicate, `ValueError` SHALL be raised.

#### Scenario: Duplicate note within window

- GIVEN note "Hello World" by authorA created 1s ago
- WHEN `create_note(ticket_id, authorA, "  hello world  ")` is called
- THEN `ValueError` is raised (duplicate)

#### Scenario: Same content outside window

- GIVEN note "Hello" by authorA created 5s ago
- WHEN `create_note(ticket_id, authorA, "hello")` is called
- THEN the note is created

#### Scenario: Different author same content

- GIVEN note "Hello" by authorA created 1s ago
- WHEN `create_note(ticket_id, authorB, "hello")` is called
- THEN the note is created (different author, no dedup)

### Requirement: Audit logging on ticket operations

Every ticket operation (claim, close, reopen, transfer, subticket create, note add, note list, note delete) MUST write a `ticket_audit` row with ticketId, action, actorId, outcome, reason, timestamp. Guild-scoped queries.

#### Scenario: Claim audited on success

- GIVEN a mod claims ticket #5
- WHEN the claim succeeds
- THEN audit row (action=claim, outcome=success) is written

#### Scenario: Invariant violation audited

- GIVEN a non-mod attempts claim
- WHEN access is denied
- THEN audit row (action=claim, outcome=denied, reason) is written
