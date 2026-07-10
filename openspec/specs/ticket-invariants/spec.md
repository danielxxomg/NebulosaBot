# Ticket Invariants Specification

## Purpose

Shared source-of-truth for ticket lifecycle invariants enforced identically by bot and dashboard.

## Requirements

### Requirement: Status state machine

Ticket status MUST be one of: `open`, `claimed`, `closed`. Transitions: open→claimed (claim), open→closed (close), claimed→closed (close), closed→open (reopen, new channel), claimed→open (unclaim). Transfer reassigns `claimedBy` AND sets `status='claimed'` (implicit re-claim — transferring an open ticket claims it for the new assignee). Unclaim sets `claimedBy=null` AND `status='open'`. Invalid transitions MUST be rejected.

#### Scenario: Valid transitions

- GIVEN ticket status `open`
- WHEN claim executes
- THEN status becomes `claimed`

#### Scenario: Invalid transition rejected

- GIVEN ticket status `closed`
- WHEN claim is attempted
- THEN the operation is rejected with an error

#### Scenario: Transfer sets claimed status

- GIVEN ticket status `open` with claimedBy=null
- WHEN transfer to userB executes
- THEN claimedBy=userB and status becomes `claimed`

#### Scenario: Transfer on already-claimed ticket

- GIVEN ticket status `claimed` with claimedBy=userA
- WHEN transfer to userB executes
- THEN claimedBy=userB and status remains `claimed`

#### Scenario: Unclaim resets to open

- GIVEN ticket status `claimed` with claimedBy=userA
- WHEN unclaim executes
- THEN claimedBy=null and status becomes `open`

### Requirement: Unclaim permission check

`check_can_unclaim(actor_id, ticket)` MUST allow the operation if the actor is the current claimer OR has the mod role. All other actors MUST be denied.

#### Scenario: Claimer can unclaim

- GIVEN ticket claimed by userA
- WHEN `check_can_unclaim(userA, ticket)` is evaluated
- THEN access is granted

#### Scenario: Mod can unclaim another's ticket

- GIVEN ticket claimed by userA
- WHEN `check_can_unclaim(modUser, ticket)` is evaluated and modUser has mod role
- THEN access is granted

#### Scenario: Non-claimer non-mod denied

- GIVEN ticket claimed by userA
- WHEN `check_can_unclaim(userB, ticket)` is evaluated and userB lacks mod role
- THEN access is denied

### Requirement: Claim no-overwrite

Claim on an already-claimed ticket MUST be rejected. Reassignment SHALL use transfer only.

#### Scenario: Claim rejected when claimed

- GIVEN ticket claimed by userA
- WHEN userB attempts claim
- THEN the operation is rejected

#### Scenario: Same-user claim rejected

- GIVEN ticket claimed by userA
- WHEN userA attempts claim
- THEN the operation is rejected

### Requirement: Permission matrix

Operations × actors: create=any user; claim=mod; close=author OR mod; reopen=mod; unclaim=claimer OR mod; transfer=admin; subticket/note CRUD=admin OR mod; audit view=admin only. Dashboard actions are admin-only (divergence documented).

#### Scenario: Mod can claim

- GIVEN user has mod role
- WHEN they claim an open ticket
- THEN the claim succeeds

#### Scenario: Non-mod cannot claim

- GIVEN user lacks mod role and admin permission
- WHEN they attempt claim
- THEN access is denied

#### Scenario: Author can close own ticket

- GIVEN user is the ticket author
- WHEN they close the ticket
- THEN the close succeeds

#### Scenario: Non-author non-mod cannot close

- GIVEN user is not author and not mod
- WHEN they attempt close
- THEN access is denied

#### Scenario: Claimer can unclaim

- GIVEN user is the ticket claimer
- WHEN they unclaim the ticket
- THEN the unclaim succeeds

#### Scenario: Mod can unclaim another's ticket

- GIVEN a ticket claimed by userA
- WHEN a mod unclaims
- THEN the unclaim succeeds

#### Scenario: Non-claimer non-mod cannot unclaim

- GIVEN a ticket claimed by userA
- WHEN userB (not claimer, not mod) attempts unclaim
- THEN access is denied

### Requirement: parentId FK invariants

Subticket MUST satisfy: parent exists, same guild, parent has no `parentId` (depth max 2), not self-referential.

#### Scenario: Valid subticket

- GIVEN parent exists in guild G with no parentId
- WHEN subticket is created with parentId=parent
- THEN creation succeeds

#### Scenario: Depth limit enforced

- GIVEN parent ticket already has a parentId
- WHEN subticket targets that parent
- THEN creation is rejected

#### Scenario: Cross-guild rejected

- GIVEN parent is in guild A
- WHEN subticket targets that parent from guild B
- THEN creation is rejected

### Requirement: Idempotency rules

Status guards: reopen only if status==closed; transfer only if claimedBy!=target. Note dedup: SHA256 of `trim(content).lower().collapse_whitespace()` vs same authorId within 2s window.

#### Scenario: Reopen on open ticket rejected

- GIVEN ticket status `open`
- WHEN reopen is attempted
- THEN the operation is rejected

#### Scenario: Transfer to same user rejected

- GIVEN ticket claimed by userA
- WHEN transfer to userA is attempted
- THEN the operation is rejected

#### Scenario: Duplicate note rejected

- GIVEN note "Hello World" by authorA exists (created 1s ago)
- WHEN authorA submits "  hello world  "
- THEN the note is rejected as duplicate

#### Scenario: Same content outside window allowed

- GIVEN note "Hello" by authorA (created 5s ago)
- WHEN authorA submits "hello"
- THEN the note is created

### Requirement: Audit logging

Every operation and invariant violation MUST write a `ticket_audit` row: ticketId, action, actorId, outcome (success|denied|error), reason, createdAt. Queries MUST be guild-scoped.

#### Scenario: Successful operation audited

- GIVEN a mod claims an open ticket
- WHEN the claim succeeds
- THEN audit row (outcome=success) is written

#### Scenario: Denied operation audited

- GIVEN a non-mod attempts claim
- WHEN access is denied
- THEN audit row (outcome=denied, reason) is written

#### Scenario: Guild-scoped audit query

- GIVEN audit rows for guilds A and B
- WHEN querying audit for guild A
- THEN only guild A rows return
