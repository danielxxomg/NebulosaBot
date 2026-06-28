# Ticket Views Specification

## Purpose

Define persistent Discord UI components for ticket panels and per-ticket actions.

## Requirements

### Requirement: Ticket panel view

The system MUST provide a persistent panel view with a category dropdown and an open button.

#### Scenario: Panel render

- GIVEN a guild with at least one ticket category
- WHEN the panel is deployed
- THEN the message displays a category select menu and an open ticket button

#### Scenario: Open ticket from panel

- GIVEN a user selects a category from the panel dropdown
- WHEN the user clicks the open button
- THEN a new ticket is created for that category

#### Scenario: Empty category list

- GIVEN a guild with no ticket categories
- WHEN the panel is rendered
- THEN the dropdown is disabled and a placeholder indicates no categories configured

### Requirement: Ticket actions view

The system MUST provide a per-ticket action view with close and claim buttons.

#### Scenario: Action view render

- GIVEN a newly created ticket channel
- WHEN the ticket is opened
- THEN an embed with close and claim buttons is sent in the channel

#### Scenario: Close from action view

- GIVEN an open ticket channel with the action view
- WHEN a staff member clicks close
- THEN the ticket close flow is triggered

#### Scenario: Claim from action view

- GIVEN an open ticket channel with the action view
- WHEN a staff member clicks claim
- THEN the ticket claim flow is triggered

### Requirement: View persistence

The system MUST re-register persistent views on bot startup so buttons remain functional after restart.

#### Scenario: Bot restart

- GIVEN a deployed panel or active ticket view
- WHEN the bot restarts
- THEN the views are re-registered and interactions continue to work
