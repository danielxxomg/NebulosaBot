# Delta for Ticket Views

## MODIFIED Requirements

### Requirement: Ticket panel view

The system MUST provide a persistent panel view with an open button. `TicketPanelView`, `TicketActionsView`, and `_CategorySelectView` MUST reside in `bot/views/tickets.py`. Panel design: the open button triggers an ephemeral category dropdown after click. Button labels MUST be resolved dynamically via `t()` at interaction time using `interaction.guild_id`, not only at construction time.

(Previously: labels were set only at construction; after restart, English defaults persisted for non-English guilds)

#### Scenario: Panel render

- GIVEN a guild with at least one ticket category
- WHEN the panel is deployed
- THEN the message displays an open ticket button

#### Scenario: Open ticket from panel

- GIVEN a user clicks the open button on the panel
- WHEN categories exist
- THEN an ephemeral category select dropdown is shown; upon selection a new ticket is created

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

### Requirement: Ticket actions view

The system MUST provide a per-ticket action view with close and claim buttons. Claim button MUST be gated by `@is_mod()` (solo mod). Close button MUST be gated by author OR mod. Non-eligible users clicking a gated button SHALL receive an ephemeral rejection message. Button labels MUST be resolved dynamically via `t()` at interaction time using `interaction.guild_id`.

(Previously: labels were set only at construction; action button labels did not update for non-English guilds after restart)

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
- THEN the ticket close flow is triggered

#### Scenario: Mod clicks close on another's ticket

- GIVEN a ticket authored by userA
- WHEN a mod (not userA) clicks close
- THEN the ticket close flow is triggered

#### Scenario: Non-author non-mod clicks close rejected

- GIVEN a ticket authored by userA
- WHEN userB (not author, not mod) clicks close
- THEN an ephemeral rejection message is sent

#### Scenario: Close from action view

- GIVEN an open ticket channel with the action view
- WHEN a staff member clicks close
- THEN the ticket close flow is triggered

#### Scenario: Claim from action view

- GIVEN an open ticket channel with the action view
- WHEN a staff member clicks claim
- THEN the ticket claim flow is triggered

#### Scenario: Localized action labels after restart

- GIVEN a Spanish guild with an active ticket
- WHEN the bot restarts and a user clicks Claim
- THEN the claim button label is resolved via `t('tickets.actions.claim_button', guild_id)` at interaction time
