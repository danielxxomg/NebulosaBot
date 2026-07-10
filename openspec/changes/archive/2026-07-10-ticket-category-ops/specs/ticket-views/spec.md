# Delta for Ticket Views

## ADDED Requirements

### Requirement: Edit category button in ticket actions

`TicketActionsView` MUST include an "Edit Category" button alongside Claim and Close. The button MUST be gated by `@is_mod()` — non-mod users clicking it SHALL receive an ephemeral rejection message. On click, the system SHALL fetch active categories for the guild and display an ephemeral `_CategorySelect` dropdown. The select callback MUST re-run `is_mod_check()` on submit (the ephemeral select persists 300s; a non-mod could click it after the opening mod left) and reject non-mods with an ephemeral message. The select callback MUST also reject closed tickets. On selection, the system SHALL call `edit_ticket_category()` and confirm success with an ephemeral message. When the service raises `ValueError` due to the one-ticket-per-user-per-category limit, the view MUST surface the specific `tickets.actions.edit_category_limit_*` ephemeral message (NOT a generic `creation_failed`), because the duplicate is created by the edit, not by ticket creation. Button label MUST be resolved dynamically via `t()` at interaction time.

#### Scenario: Mod clicks edit category

- GIVEN an open ticket with the action view
- WHEN a mod clicks "Edit Category"
- THEN an ephemeral category select dropdown is shown

#### Scenario: Category selection triggers edit

- GIVEN the ephemeral category dropdown is shown
- WHEN a mod selects "Billing"
- THEN `edit_ticket_category()` is called and a success message is shown

#### Scenario: Non-mod clicks edit category rejected

- GIVEN an open ticket with the action view
- WHEN a non-mod user clicks "Edit Category"
- THEN an ephemeral rejection message is sent

#### Scenario: Selector re-checks mod on submit

- GIVEN the ephemeral select dropdown was opened by a mod 200s ago
- WHEN a non-mod submits a selection from the same view
- THEN `is_mod_check()` rejects the submit and an ephemeral rejection message is sent (no edit call)

#### Scenario: Selector rejects closed ticket

- GIVEN a ticket became closed while the ephemeral select was open
- WHEN a mod submits a category selection
- THEN the submit is rejected with an ephemeral message (edit_category is not valid on closed tickets)

#### Scenario: Limit violation shows specific UX

- GIVEN a mod edits ticket B and the author already has an open ticket in the target category
- WHEN `edit_ticket_category()` raises `ValueError` (one per user per category)
- THEN the view shows the specific `tickets.actions.edit_category_limit_*` ephemeral message (NOT a generic `creation_failed`)

#### Scenario: Channel rename failure shows warning

- GIVEN the category edit succeeds in DB but channel rename fails
- WHEN the mod selects a new category
- THEN an ephemeral message confirms DB update and warns about channel name

#### Scenario: No active categories

- GIVEN a guild with no active ticket categories
- WHEN a mod clicks "Edit Category"
- THEN an ephemeral message indicates no categories are available

### Requirement: Edit category button label localization

The "Edit Category" button label MUST be resolved via `t('tickets.actions.edit_category', guild_id)` at interaction time, consistent with Claim and Close button localization.

#### Scenario: Localized edit button after restart

- GIVEN a Spanish guild with an active ticket
- WHEN the bot restarts and a mod views the ticket actions
- THEN the edit category button label is resolved via `t()` at interaction time
