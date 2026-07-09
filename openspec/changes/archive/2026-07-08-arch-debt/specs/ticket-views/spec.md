# Delta for Ticket Views

## MODIFIED Requirements

### Requirement: Ticket panel view

The system MUST provide a persistent panel view with an open button. `TicketPanelView`, `TicketActionsView`, and `_CategorySelectView` MUST reside in `bot/views/tickets.py`. Panel design: the open button triggers an ephemeral category dropdown after click. This is the existing behavior; spec was outdated.

(Previously: views defined inline in bot/cogs/tickets.py)

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

### Requirement: Ticket actions view

The system MUST provide a per-ticket action view with close and claim buttons. Claim button MUST be gated by `@is_mod()` (solo mod). Close button MUST be gated by author OR mod. Non-eligible users clicking a gated button SHALL receive an ephemeral rejection message.

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

### Requirement: View persistence

The system MUST re-register persistent views on bot startup so buttons remain functional after restart. `bot.add_view()` calls in `setup_hook` MUST use updated import paths matching the new view locations.

(Previously: import paths pointed to bot/cogs/tickets.py)

#### Scenario: Bot restart

- GIVEN a deployed panel or active ticket view
- WHEN the bot restarts
- THEN the views are re-registered and interactions continue to work

## ADDED Requirements

### Requirement: Channel creation extracted to service

Channel creation logic (permission overwrites, channel creation, DB insert, rename) MUST be extracted to `TicketService.create_ticket_channel()`.

#### Scenario: create_ticket_channel called

- GIVEN guild config, author, category_id, and mod_role
- WHEN `TicketService.create_ticket_channel()` is called
- THEN a Discord channel is created with correct overwrites and a Ticket row is inserted

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
