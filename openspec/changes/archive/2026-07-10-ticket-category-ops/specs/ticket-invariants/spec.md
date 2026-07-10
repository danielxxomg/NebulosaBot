# Delta for Ticket Invariants

## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Permission matrix

Operations × actors: create=any user; claim=mod; close=author OR mod; reopen=mod; unclaim=claimer OR mod; transfer=admin; edit_category=mod; subticket/note CRUD=admin OR mod; audit view=admin only. Dashboard actions are admin-only (divergence documented).

(Previously: edit_category was not listed)

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
