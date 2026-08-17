# Ticket Invariants Specification

## Purpose

Shared source-of-truth for ticket lifecycle invariants enforced identically by bot and dashboard.

## Requirements

### Requirement: One open ticket per user per category

`check_one_ticket_per_user_per_category(user_id, category_id, parent_id, count_fn)` MUST raise `ValueError` when the user already has an open ticket (status `open` or `claimed`) in the given category. The check MUST be skipped when `parent_id` is not None (subticket carve-out). The check MUST be skipped when `category_id` is null (uncategorized tickets have no limit). This is a pure function — `count_fn` is injected for testability.

#### Scenario: User with open ticket blocked

- GIVEN userA has 1 open ticket in category "Support"
- WHEN `check_one_ticket_per_user_per_category(userA, "Support", None, count_fn)` is called
- THEN `ValueError` is raised

#### Scenario: User with claimed ticket blocked

- GIVEN userA has 1 claimed ticket in category "Support"
- WHEN `check_one_ticket_per_user_per_category(userA, "Support", None, count_fn)` is called
- THEN `ValueError` is raised (claimed counts as open)

#### Scenario: User with no open tickets allowed

- GIVEN userA has 0 open tickets in category "Support"
- WHEN `check_one_ticket_per_user_per_category(userA, "Support", None, count_fn)` is called
- THEN no error is raised

#### Scenario: Subticket skips check

- GIVEN userA has 1 open ticket in category "Support"
- WHEN `check_one_ticket_per_user_per_category(userA, "Support", parent_id=abc, count_fn)` is called
- THEN no error is raised (subticket carve-out)

#### Scenario: Null categoryId skips check

- GIVEN userA has 1 open ticket with categoryId=null
- WHEN `check_one_ticket_per_user_per_category(userA, null, None, count_fn)` is called
- THEN no error is raised

#### Scenario: Closed ticket frees slot

- GIVEN userA has 1 closed ticket and 0 open tickets in "Support"
- WHEN `check_one_ticket_per_user_per_category(userA, "Support", None, count_fn)` is called
- THEN no error is raised

### Requirement: Edit category permission check

`check_can_edit_category(actor_id, ticket, *, is_mod)` MUST allow the operation if the actor has the mod role or admin permission. Ticket authors without mod role MUST be denied. The `is_mod` keyword is the caller-supplied resolved mod/admin flag, matching the `check_can_unclaim(actor_id, ticket, *, is_mod)` signature so the pure invariant is not coupled to Discord objects. The service re-validates with this helper on every `edit_ticket_category` call (it is the security boundary), and the view additionally gates UX via `is_mod_check()`.

#### Scenario: Mod can edit category

- GIVEN a ticket in the guild
- WHEN `check_can_edit_category(modUser, ticket, is_mod=True)` is evaluated
- THEN access is granted

#### Scenario: Non-mod author denied

- GIVEN a ticket authored by userA
- WHEN `check_can_edit_category(userA, ticket, is_mod=False)` is evaluated
- THEN access is denied

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

Operations × actors: create=any user; claim=mod; close=author OR mod; reopen=mod; unclaim=claimer OR mod; transfer=admin; edit_category=mod; subticket/note CRUD=admin OR mod; audit view=admin only. Dashboard actions are admin-only (divergence documented).

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

#### Scenario: Mod can edit category

- GIVEN a ticket in the guild
- WHEN a mod edits the ticket category
- THEN the category edit succeeds

#### Scenario: Non-mod cannot edit category

- GIVEN a ticket authored by userA
- WHEN userA (not mod) attempts to edit category
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

<!-- BEGIN DELTA: product-artifact-audit (ticket-invariants) -->
## ADDED Requirements

### Requirement: Two-factor repair invariant

Automatic repair MUST be authorized only when the deployment/schema preflight is verified and the per-ticket Discord evidence is fresh, unambiguous, guild-matched, and corroborates channel absence for an active ticket. Any missing, stale, future-dated, transient, or ambiguous input MUST fail closed to quarantine/report/no-op. The channel deletion actor MUST NOT participate in this decision.

#### Scenario: Both gates permit repair

- GIVEN verified live preflight and fresh corroborated evidence for an active ticket
- WHEN the repair invariant is evaluated
- THEN automatic mutation is permitted

#### Scenario: Stale preflight blocks repair

- GIVEN schema evidence is stale or deployment compatibility is unverified
- WHEN fresh channel-absence evidence is evaluated
- THEN the invariant denies mutation and requires a reviewable result

#### Scenario: Ambiguous evidence blocks repair

- GIVEN Discord evidence is unknown, contradictory, or not per-ticket
- WHEN repair authorization is evaluated
- THEN mutation is denied and no state transition is allowed

### Requirement: Scoped repair authority

Guild administrators MUST be authorized only for operations targeting their own guild. Bot operators MAY diagnose across guilds, but operator mutation authority MUST be an explicit operation-level grant and MUST be recorded with actor, scope, target guild, and outcome. No caller role or audit-log attribution MAY implicitly grant mutation authority.

#### Scenario: Same-guild admin allowed

- GIVEN an administrator targets a corroborated ticket in their guild
- WHEN authority is evaluated
- THEN the guild-scoped operation may proceed through the shared service path

#### Scenario: Cross-guild admin denied

- GIVEN an administrator for guild A targets guild B
- WHEN authority is evaluated
- THEN mutation is denied and the target ticket remains unchanged

#### Scenario: Global diagnosis is read-only

- GIVEN an operator has global diagnosis but no explicit mutation grant
- WHEN the operator requests a repair
- THEN diagnosis is allowed, mutation is denied, and the denial is auditable

### Requirement: Audit invariant for outcomes

Every denied or failed repair MUST produce best-effort audit evidence with a non-empty reason. Quarantine and no-op outcomes MUST NOT be recorded as successful mutation. Duplicate-event losers MUST produce a deterministic denied/no-op audit outcome without a second success transition; audit-write failure MUST be logged and MUST NOT create a false success claim.

#### Scenario: Denied operation is reviewable

- GIVEN a permission or evidence gate denies repair
- WHEN the operation returns
- THEN a non-empty denied/quarantine reason is available to audit and review

#### Scenario: No-op is not mutation

- GIVEN a ticket is already closed or no safe candidate exists
- WHEN repair completes
- THEN no success mutation audit is written

<!-- END DELTA: product-artifact-audit (ticket-invariants) -->
