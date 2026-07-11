# Delta for ticket-views

## MODIFIED Requirements

### Requirement: Edit category button in ticket actions

`TicketActionsView` MUST include an "Edit Category" button alongside Claim and Close. The button MUST be gated by `@is_mod()` — non-mod users clicking it SHALL receive an ephemeral rejection message. On click, the system SHALL fetch active categories for the guild and display an ephemeral `_CategorySelect` dropdown. The select callback MUST re-run `is_mod_check()` on submit (the ephemeral select persists 300s; a non-mod could click it after the opening mod left) and reject non-mods with an ephemeral message. The select callback MUST also reject closed tickets. On selection, the system SHALL call `edit_ticket_category()` and confirm success with an ephemeral message. When the service raises `ValueError` due to the one-ticket-per-user-per-category limit, the view MUST surface the specific `tickets.actions.edit_category_limit_*` ephemeral message (NOT a generic `creation_failed`), because the duplicate is created by the edit, not by ticket creation. After the ephemeral success, the system MUST send a non-ephemeral `info_embed` to the ticket channel showing old category, new category, and actor mention, using `tickets.actions.edit_category_audit_title` and `tickets.actions.edit_category_audit_description` i18n keys. Old category name MUST be resolved from the pre-update `ticket_row["categoryId"]` via `self.options`; when the previous `categoryId` is `None`, the system MUST fall back to `"—"`. If `channel.send()` raises `discord.HTTPException`, the system MUST catch the exception, log a warning, and the edit MUST still be considered successful. Button label MUST be resolved dynamically via `t()` at interaction time.

(Previously: ephemeral success only — no channel-visible audit message after category edit)

#### Scenario: Mod clicks edit category

- GIVEN an open ticket with the action view
- WHEN a mod clicks "Edit Category"
- THEN an ephemeral category select dropdown is shown

#### Scenario: Category selection triggers edit and sends audit embed

- GIVEN the ephemeral category dropdown is shown
- WHEN a mod selects "Billing"
- THEN `edit_ticket_category()` is called, an ephemeral success message is shown to the actor, AND a non-ephemeral `info_embed` is sent to the ticket channel showing old → new category with actor mention

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

#### Scenario: Audit embed old category fallback when categoryId is None

- GIVEN a ticket with `categoryId = None` (pre-category ticket)
- WHEN a mod edits the category
- THEN the audit embed shows `"—"` as the old category

#### Scenario: Audit embed send failure is non-fatal

- GIVEN the category edit succeeds in DB
- WHEN `channel.send(embed=...)` raises `discord.HTTPException`
- THEN the edit is still considered successful and a warning is logged
