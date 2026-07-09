# Delta for Ticket Views

## MODIFIED Requirements

### Requirement: Ticket panel view

The system MUST provide a persistent panel view with an open button. `TicketPanelView`, `TicketActionsView`, and `_CategorySelectView` MUST reside in `bot/views/tickets.py`. Panel design: the open button triggers an ephemeral category dropdown after click. Button labels MUST be resolved dynamically via `t()` at interaction time using `interaction.guild_id`, not only at construction time. On category selection, the system SHALL respond with a `TicketIntakeModal` instead of deferring immediately.

(Previously: category select deferred immediately; no modal was shown)

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

### Requirement: Channel creation extracted to service

Channel creation logic (permission overwrites, channel creation, DB insert, rename) MUST be extracted to `TicketService.create_ticket_channel()`. The modal submit callback SHALL call `create_ticket_channel()` with `subject` and `description` parameters.

(Previously: create_ticket_channel did not accept subject/description)

#### Scenario: create_ticket_channel called

- GIVEN guild config, author, category_id, and mod_role
- WHEN `TicketService.create_ticket_channel()` is called
- THEN a Discord channel is created with correct overwrites and a Ticket row is inserted

#### Scenario: create_ticket_channel with subject and description

- GIVEN modal-submitted subject and description
- WHEN `TicketService.create_ticket_channel(subject=..., description=...)` is called
- THEN the Ticket row includes the subject and description values

## ADDED Requirements

### Requirement: Welcome embed pinned after creation

After sending the welcome embed with `TicketActionsView` in a new ticket channel, the system SHALL call `message.pin()` to pin the welcome embed.

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
