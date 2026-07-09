# Delta for Ticket Invariants

## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Status state machine

Ticket status MUST be one of: `open`, `claimed`, `closed`. Transitions: open→claimed (claim), open→closed (close), claimed→closed (close), closed→open (reopen, new channel), claimed→open (unclaim). Transfer reassigns `claimedBy` AND sets `status='claimed'` (implicit re-claim — transferring an open ticket claims it for the new assignee). Unclaim sets `claimedBy=null` AND `status='open'`. Invalid transitions MUST be rejected.

(Previously: no claimed→open transition existed)

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

### Requirement: Permission matrix

Operations × actors: create=any user; claim=mod; close=author OR mod; reopen=mod; unclaim=claimer OR mod; transfer=admin; subticket/note CRUD=admin OR mod; audit view=admin only. Dashboard actions are admin-only (divergence documented).

(Previously: unclaim was not in the permission matrix)

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
