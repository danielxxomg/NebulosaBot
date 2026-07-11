# Ticket Views Specification

## Purpose

Define persistent Discord UI components for ticket panels and per-ticket actions.

## Requirements

### Requirement: Ticket panel view

The system MUST provide a persistent panel view with an open button. `TicketPanelView`, `TicketActionsView`, and `_CategorySelectView` MUST reside in `bot/views/tickets.py`. Panel design: the open button triggers an ephemeral category dropdown after click. Button labels MUST be resolved dynamically via `t()` at interaction time using `interaction.guild_id`, not only at construction time. On category selection, the system SHALL respond with a `TicketIntakeModal` that receives the selected category's `field_definitions` for dynamic TextInput construction.

#### Scenario: Panel render

- GIVEN a guild with at least one ticket category
- WHEN the panel is deployed
- THEN the message displays an open ticket button

#### Scenario: Open ticket from panel

- GIVEN a user clicks the open button on the panel
- WHEN categories exist
- THEN an ephemeral category select dropdown is shown; upon selection a modal is displayed

#### Scenario: Empty category list

- GIVEN a guild with no ticket categories
- WHEN a user clicks the open button
- THEN an ephemeral error message indicates no categories are configured

#### Scenario: Views importable from new location

- GIVEN views are extracted to `bot/views/tickets.py`
- WHEN `bot/bot.py` imports `TicketPanelView` and `TicketActionsView`
- THEN the import succeeds from the new path

#### Scenario: Localized labels after restart

- GIVEN a Spanish guild with a deployed ticket panel
- WHEN the bot restarts and a user clicks the open button
- THEN the button label is resolved via `t('tickets.panel.open_button', guild_id)` at interaction time

#### Scenario: English fallback before first interaction

- GIVEN any guild with a deployed ticket panel
- WHEN the bot restarts and the panel has not yet been interacted with
- THEN the button shows the English decorator default until first interaction updates it

#### Scenario: Category select passes field_definitions to modal

- GIVEN a category with `field_definitions = [{key: "player_nick", label: "Player Nickname", style: "short", required: true}]`
- WHEN a user selects that category
- THEN `TicketIntakeModal` is constructed with `field_definitions=[{...}]`

#### Scenario: Category select with no field_definitions

- GIVEN a category with `field_definitions = []`
- WHEN a user selects that category
- THEN `TicketIntakeModal` is constructed with `field_definitions=[]`

### Requirement: Ticket actions view

The system MUST provide a per-ticket action view with close and claim buttons. Claim button MUST be gated by `@is_mod()` (solo mod). Close button MUST be gated by author OR mod. Non-eligible users clicking a gated button SHALL receive an ephemeral rejection message. Button labels MUST be resolved dynamically via `t()` at interaction time using `interaction.guild_id`. Close button click MUST trigger an ephemeral `ConfirmCancelView` confirmation dialog before proceeding. Claim on an already-claimed ticket MUST trigger an ephemeral transfer confirmation dialog before calling `transfer_ticket()`.

#### Scenario: Action view render

- GIVEN a newly created ticket channel
- WHEN the ticket is opened
- THEN an embed with close and claim buttons is sent in the channel

#### Scenario: Mod clicks claim

- GIVEN an open ticket with the action view
- WHEN a mod clicks claim
- THEN the ticket claim flow is triggered

#### Scenario: Non-mod clicks claim rejected

- GIVEN an open ticket with the action view
- WHEN a non-mod user clicks claim
- THEN an ephemeral rejection message is sent

#### Scenario: Author clicks close

- GIVEN a ticket authored by userA
- WHEN userA clicks close
- THEN an ephemeral Confirm/Cancel confirmation dialog is shown

#### Scenario: Mod clicks close on another's ticket

- GIVEN a ticket authored by userA
- WHEN a mod (not userA) clicks close
- THEN an ephemeral Confirm/Cancel confirmation dialog is shown

#### Scenario: Non-author non-mod clicks close rejected

- GIVEN a ticket authored by userA
- WHEN userB (not author, not mod) clicks close
- THEN an ephemeral rejection message is sent

#### Scenario: Close from action view

- GIVEN an open ticket channel with the action view
- WHEN a staff member clicks close and confirms
- THEN the ticket close flow is triggered with countdown

#### Scenario: Claim from action view

- GIVEN an open ticket channel with the action view
- WHEN a staff member clicks claim
- THEN the ticket claim flow is triggered

#### Scenario: Localized action labels after restart

- GIVEN a Spanish guild with an active ticket
- WHEN the bot restarts and a user clicks Claim
- THEN the claim button label is resolved via `t('tickets.actions.claim_button', guild_id)` at interaction time

#### Scenario: Claim on already-claimed ticket shows transfer confirm

- GIVEN a ticket claimed by userA
- WHEN userB (mod) clicks Claim
- THEN an ephemeral transfer confirmation dialog is shown with "Transfer ticket from userA to userB?"

#### Scenario: Transfer confirm proceeds

- GIVEN a claim-on-claimed transfer confirmation dialog
- WHEN the mod clicks Confirm
- THEN `transfer_ticket()` is called and the ticket is reassigned to userB

### Requirement: Reopen command accepts ticket-id

The `/reopen` command MUST accept an optional ticket-id argument (e.g. `/reopen ticket:#<number>` or `/reopen <uuid>`) so it can be invoked from any channel — the original ticket channel is deleted on close, making the current channel-scoped lookup unusable for closed tickets. When the ticket-id argument is provided, the command resolves the ticket by id (not by current channel). When omitted, the current behavior (resolve by channel) is preserved for the 5-second window between `status=closed` and `channel.delete()`.

(Previously: `/reopen` resolved the ticket by `ctx.channel.id` only — broken for any closed ticket whose channel was deleted, which is all of them after the 5-second close window)

#### Scenario: Reopen by ticket-id from any channel

- GIVEN a closed ticket #3 whose channel was deleted
- WHEN a mod runs `/reopen ticket:#0003` from any channel
- THEN the bot resolves ticket #3 by id and creates a new channel

#### Scenario: Reopen by channel (legacy window)

- GIVEN a ticket just closed (status=closed, channel still exists in the 5s window)
- WHEN a mod runs `/reopen` (no arg) in that channel
- THEN the bot resolves the ticket by current channel and creates a new channel

#### Scenario: Reopen non-closed ticket rejected

- GIVEN ticket #3 has status `open`
- WHEN a mod runs `/reopen ticket:#0003`
- THEN the operation is rejected (status-guard: reopen only if status==closed)

### Requirement: View persistence

The system MUST re-register persistent views on bot startup so buttons remain functional after restart. `bot.add_view()` calls in `setup_hook` MUST use updated import paths matching the new view locations.

(Previously: import paths pointed to bot/cogs/tickets.py)

#### Scenario: Bot restart

- GIVEN a deployed panel or active ticket view
- WHEN the bot restarts
- THEN the views are re-registered and interactions continue to work

### Requirement: Channel creation extracted to service

Channel creation logic (permission overwrites, channel creation, DB insert, rename) MUST be extracted to `TicketService.create_ticket_channel()`. The modal submit callback SHALL call `create_ticket_channel()` with `subject` and `description` parameters.

#### Scenario: create_ticket_channel called

- GIVEN guild config, author, category_id, and mod_role
- WHEN `TicketService.create_ticket_channel()` is called
- THEN a Discord channel is created with correct overwrites and a Ticket row is inserted

#### Scenario: create_ticket_channel with subject and description

- GIVEN modal-submitted subject and description
- WHEN `TicketService.create_ticket_channel(subject=..., description=...)` is called
- THEN the Ticket row includes the subject and description values

### Requirement: Close flow extracted to service

Close flow (transcript generation, log channel upload, DB close, channel delete) MUST be extracted to `TicketService.close_ticket_full()`.

#### Scenario: close_ticket_full called

- GIVEN an open ticket with messages
- WHEN `TicketService.close_ticket_full()` is called
- THEN transcript is generated, uploaded, DB row updated to closed, and channel deleted

### Requirement: Ticket-by-channel lookup helper

A `resolve_ticket_for_channel()` helper MUST exist in `bot/utils/ticket_helpers.py` that encapsulates ticket-by-channel lookup, null check, and error handling.

#### Scenario: Valid channel lookup

- GIVEN a channel that has an open ticket
- WHEN `resolve_ticket_for_channel(bot, channel_id, guild_id)` is called
- THEN the ticket dict is returned

#### Scenario: No ticket for channel

- GIVEN a channel with no associated ticket
- WHEN `resolve_ticket_for_channel()` is called
- THEN `None` is returned

### Requirement: tickets.py line count reduction

After extraction, `bot/cogs/tickets.py` MUST be under ~600 lines (from 2015). The original ~500 target was aspirational; 571 represents a 71% reduction and is within tolerance for the "lean command cog" intent. The remaining lines are `_err/_ok/_info` helpers, `on_message` listener, and auto-close task — all of which belong in the cog.

#### Scenario: Line count after extraction

- GIVEN all views, embeds, channel creation, close flow, and lookup helpers are extracted
- WHEN `wc -l bot/cogs/tickets.py` is run
- THEN the result is under ~600 lines

### Requirement: Welcome embed pinned after creation

After sending the welcome embed with `TicketActionsView` in a new ticket channel, the system SHALL call `message.pin()` to pin the welcome embed. The welcome embed MUST render any `custom_fields` values as inline fields below the subject/description.

#### Scenario: Welcome embed pinned

- GIVEN a new ticket channel is created
- WHEN the welcome embed is sent
- THEN the embed message is pinned in the channel

#### Scenario: Embed title uses subject

- GIVEN a ticket with subject="Login broken"
- WHEN `build_ticket_embed()` is called
- THEN the embed title is "#0003 — Login broken"

#### Scenario: Embed title fallback when no subject

- GIVEN a ticket with subject=null
- WHEN `build_ticket_embed()` is called
- THEN the embed title is "Ticket #0003"

#### Scenario: Embed renders custom fields

- GIVEN a ticket with `custom_fields = {"player_nick": "DarkSlayer42", "evidence_url": "https://imgur.com/..."}`
- WHEN `build_ticket_embed()` is called
- THEN the embed includes inline fields for "Player Nickname" and "Evidence URL" with their values

#### Scenario: Embed handles missing custom fields

- GIVEN a ticket with `custom_fields = {}` or `null`
- WHEN `build_ticket_embed()` is called
- THEN the embed renders normally without custom field sections

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

### Requirement: Edit category button label localization

The "Edit Category" button label MUST be resolved via `t('tickets.actions.edit_category', guild_id)` at interaction time, consistent with Claim and Close button localization.

#### Scenario: Localized edit button after restart

- GIVEN a Spanish guild with an active ticket
- WHEN the bot restarts and a mod views the ticket actions
- THEN the edit category button label is resolved via `t()` at interaction time
