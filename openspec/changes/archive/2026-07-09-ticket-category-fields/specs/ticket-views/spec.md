# Delta for Ticket Views

## MODIFIED Requirements

### Requirement: Ticket panel view

The system MUST provide a persistent panel view with an open button. `TicketPanelView`, `TicketActionsView`, and `_CategorySelectView` MUST reside in `bot/views/tickets.py`. Panel design: the open button triggers an ephemeral category dropdown after click. Button labels MUST be resolved dynamically via `t()` at interaction time using `interaction.guild_id`, not only at construction time. On category selection, the system SHALL respond with a `TicketIntakeModal` that receives the selected category's `field_definitions` for dynamic TextInput construction.

(Previously: modal received no field_definitions; only title+description were shown)

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

### Requirement: Welcome embed pinned after creation

After sending the welcome embed with `TicketActionsView` in a new ticket channel, the system SHALL call `message.pin()` to pin the welcome embed. The welcome embed MUST render any `custom_fields` values as inline fields below the subject/description.

(Previously: embed did not render custom_fields)

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
