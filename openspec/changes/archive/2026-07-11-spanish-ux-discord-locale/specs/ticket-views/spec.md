# Delta for ticket-views

## MODIFIED Requirements

### Requirement: Ticket panel view

The system MUST provide a persistent panel view with an open button. `TicketPanelView`, `TicketActionsView`, and `_CategorySelectView` MUST reside in `bot/views/tickets.py`. Panel design: the open button triggers an ephemeral category dropdown after click. Button labels MUST be resolved dynamically via `t()` at interaction time using `interaction.guild_id`, not only at construction time. On category selection, the system SHALL respond with a `TicketIntakeModal` that receives the selected category's `field_definitions` for dynamic TextInput construction. Default panel title and description MUST be resolved via `t()` keys, not hardcoded English strings. The `/ticket_panel` command MUST default `title` and `description_text` to `None` (not English strings); when `None`, `deploy_ticket_panel` resolves the localized default via `t(guild_id, ...)`. Explicit admin-provided values override the localized defaults. The self-heal panel deploy flow MUST pass `guild_id` to resolve default strings via `t()`.

(Previously: decorator defaults were hardcoded English; panel defaults used hardcoded English constants)

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

#### Scenario: Spanish-first decorator defaults

- GIVEN any guild with a deployed ticket panel
- WHEN the bot restarts and the panel has not yet been interacted with
- THEN the button shows the Spanish decorator default (not English)

#### Scenario: Category select passes field_definitions to modal

- GIVEN a category with `field_definitions = [{key: "player_nick", label: "Player Nickname", style: "short", required: true}]`
- WHEN a user selects that category
- THEN `TicketIntakeModal` is constructed with `field_definitions=[{...}]`

#### Scenario: Category select with no field_definitions

- GIVEN a category with `field_definitions = []`
- WHEN a user selects that category
- THEN `TicketIntakeModal` is constructed with `field_definitions=[]`

#### Scenario: Self-heal panel deploy uses guild language

- GIVEN a Spanish guild with a deployed panel
- WHEN the self-heal flow re-deploys the panel
- THEN the default title and description are resolved via `t()` using the guild's language

#### Scenario: Admin /ticket_panel with no overrides uses localized defaults

- GIVEN a Spanish guild
- WHEN an admin runs `/ticket_panel` without providing title or description
- THEN the command args are `None` (not English strings) and `deploy_ticket_panel` resolves the panel title and description via `t(guild_id, ...)`

#### Scenario: Admin /ticket_panel with explicit overrides

- GIVEN any guild
- WHEN an admin runs `/ticket_panel title:"Mi Panel" description_text:"Abre un ticket"`
- THEN those explicit values are passed through to `deploy_ticket_panel` as-is, overriding localized defaults
