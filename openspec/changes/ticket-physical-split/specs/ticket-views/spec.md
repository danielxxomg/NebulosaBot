# Delta for Ticket Views

## MODIFIED Requirements

### Requirement: Ticket panel view

The system MUST preserve a public panel-view facade while allowing `TicketPanelView`, `TicketActionsView`, and `_CategorySelectView` implementations to be split into focused modules under `bot/views/`. Their public names MUST remain importable from `bot/views/tickets.py`. Panel design: the open button triggers an ephemeral category dropdown after click. Button labels MUST be resolved dynamically via `t()` at interaction time using `interaction.guild_id`, not only at construction time. On category selection, the system SHALL respond with a `TicketIntakeModal` that receives the selected category's `field_definitions` for dynamic TextInput construction. Default panel title and description MUST be resolved via `t()` keys, not hardcoded English strings. The `/ticket_panel` command MUST default `title` and `description_text` to `None` (not English strings); when `None`, `deploy_ticket_panel` resolves the localized default via `t(guild_id, ...)`. Explicit admin-provided values override the localized defaults. The self-heal panel deploy flow MUST pass `guild_id` to resolve default strings via `t()`.

(Previously: the three view classes were required to remain physically in one module rather than behind a split-compatible facade.)

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

#### Scenario: Views importable from the facade

- GIVEN implementations are extracted to focused view modules
- WHEN `bot/bot.py` imports `TicketPanelView` and `TicketActionsView` from `bot/views/tickets.py`
- THEN the import succeeds without changing callers

#### Scenario: Localized labels after restart

- GIVEN a Spanish guild with a deployed ticket panel
- WHEN the bot restarts and a user clicks the open button
- THEN the button label is resolved via `t('tickets.panel.open_button', guild_id)` at interaction time

#### Scenario: Spanish-first decorator defaults

- GIVEN any guild with a deployed ticket panel
- WHEN the bot restarts and the panel has not yet been interacted with
- THEN the button shows the Spanish decorator default (not English)

#### Scenario: Category select passes field definitions

- GIVEN a category with `field_definitions = [{key: "player_nick", label: "Player Nickname", style: "short", required: true}]`
- WHEN a user selects that category
- THEN `TicketIntakeModal` is constructed with `field_definitions=[{...}]`

#### Scenario: Category select with no field definitions

- GIVEN a category with `field_definitions = []`
- WHEN a user selects that category
- THEN `TicketIntakeModal` receives an empty list

#### Scenario: Self-heal panel deploy uses guild language

- GIVEN a Spanish guild with a deployed panel
- WHEN self-heal re-deploys the panel
- THEN localized defaults are resolved using that guild's language

#### Scenario: Admin without overrides uses localized defaults

- GIVEN a Spanish guild
- WHEN an admin runs `/ticket_panel` without providing title or description
- THEN the command args are `None` (not English strings) and `deploy_ticket_panel` resolves the panel title and description via `t(guild_id, ...)`

#### Scenario: Explicit panel overrides win

- GIVEN any guild
- WHEN an admin runs `/ticket_panel title:"Mi Panel" description_text:"Abre un ticket"`
- THEN those explicit values are passed through to `deploy_ticket_panel` as-is, overriding localized defaults

## ADDED Requirements

### Requirement: Stable action and selector lifecycle contracts

`TicketActionsView` MUST retain `timeout=None` and the four static custom IDs `ticket:open`, `ticket:claim`, `ticket:close`, and `ticket:edit-category`; startup MUST register the persistent view with `add_view()`. Ephemeral category selectors MUST use a 300-second timeout. Their callbacks MUST re-run `is_mod_check`, re-fetch ticket state, and reject closed or unauthorized requests before mutation.

#### Scenario: Persistent IDs survive extraction

- GIVEN the bot restarts after the view split
- WHEN `setup_hook()` registers persistent views
- THEN all four IDs remain unchanged and the buttons continue working

#### Scenario: Stale ephemeral authorization is rejected

- GIVEN a selector was opened by a mod 200 seconds ago
- WHEN a now-non-mod submits it
- THEN `is_mod_check` denies the request and no edit occurs

#### Scenario: Stale ticket state is rejected

- GIVEN a ticket becomes closed while a selector remains open
- WHEN a mod submits a category selection
- THEN the callback rejects it after re-fetching state and performs no mutation
