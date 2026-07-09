# Ticket Intake Modal Specification

## Purpose

Define the modal-based ticket intake flow that collects subject and description from users after category selection.

## Requirements

### Requirement: Modal shown after category selection

The system SHALL respond to category selection with a `TicketIntakeModal` (Title required, Description optional) instead of immediately deferring.

#### Scenario: Modal appears on category select

- GIVEN a user has selected a ticket category from the panel
- WHEN the category callback fires
- THEN a modal with Title (required, short, max 100 chars) and Description (optional, paragraph, max 2000 chars) is shown

#### Scenario: Modal title includes category name

- GIVEN a user selects category "Report"
- WHEN the modal is shown
- THEN the modal title includes "Report"

### Requirement: Modal validation and submission

On `TicketIntakeModal.submit()`, the system SHALL validate that `subject` is not empty (1–100 chars), then defer the interaction and run the existing channel creation flow with `subject` and `description` passed through.

#### Scenario: Submit with both fields

- GIVEN a user fills Title="Login broken" and Description="Cannot access since Monday"
- WHEN the modal is submitted
- THEN a ticket channel is created with subject and description persisted

#### Scenario: Submit with title only

- GIVEN a user fills Title="Need help" and leaves Description empty
- WHEN the modal is submitted
- THEN a ticket channel is created with subject="Need help" and description=null

#### Scenario: Empty title rejected

- GIVEN a user submits the modal with an empty Title field
- WHEN validation runs
- THEN an ephemeral error is shown and the modal does not proceed
