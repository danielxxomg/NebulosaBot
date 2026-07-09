# Delta for Ticket Intake Modal

## MODIFIED Requirements

### Requirement: Modal shown after category selection

The system SHALL respond to category selection with a `TicketIntakeModal` that includes Title (required, short, max 100 chars), Description (optional, paragraph, max 2000 chars), and 0–3 additional TextInputs constructed from the selected category's `field_definitions`. Extra fields SHALL be inserted after Description in the modal. The modal SHALL receive `field_definitions` as a constructor parameter.

(Previously: modal showed only Title and Description with no dynamic fields)

#### Scenario: Modal appears on category select

- GIVEN a user has selected a ticket category from the panel
- WHEN the category callback fires
- THEN a modal with Title (required, short, max 100 chars) and Description (optional, paragraph, max 2000 chars) is shown

#### Scenario: Modal title includes category name

- GIVEN a user selects category "Report"
- WHEN the modal is shown
- THEN the modal title includes "Report"

#### Scenario: Modal includes dynamic fields from category config

- GIVEN a category with `field_definitions = [{key: "player_nick", label: "Player Nickname", style: "short", required: true}]`
- WHEN the modal is shown
- THEN the modal has 3 TextInputs: Title, Description, and Player Nickname

#### Scenario: Modal with no field definitions

- GIVEN a category with `field_definitions = []`
- WHEN the modal is shown
- THEN the modal has only Title and Description TextInputs

#### Scenario: Modal with max 3 field definitions

- GIVEN a category with 3 field definitions
- WHEN the modal is shown
- THEN the modal has 5 TextInputs (Title + Description + 3 custom) — the Discord maximum

### Requirement: Modal validation and submission

On `TicketIntakeModal.submit()`, the system SHALL validate that `subject` is not empty (1–100 chars), validate that all `required` custom fields are non-empty, then defer the interaction and run the existing channel creation flow with `subject`, `description`, and `custom_fields` passed through. `custom_fields` SHALL be a dict mapping each field definition `key` to the user's submitted value.

(Previously: only subject and description were collected and passed through)

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

#### Scenario: Submit with custom fields

- GIVEN a modal with Player Nickname field and user fills it with "DarkSlayer42"
- WHEN the modal is submitted
- THEN `custom_fields = {"player_nick": "DarkSlayer42"}` is passed to create_ticket_channel

#### Scenario: Required custom field empty rejected

- GIVEN a category with `player_nick` field marked as `required: true`
- WHEN the user submits the modal with an empty Player Nickname
- THEN an ephemeral error is shown and the modal does not proceed

#### Scenario: Optional custom field empty allowed

- GIVEN a category with `evidence_url` field marked as `required: false`
- WHEN the user submits the modal with an empty Evidence URL
- THEN the ticket is created with `custom_fields = {"evidence_url": null}`

#### Scenario: No field definitions skips custom fields

- GIVEN a category with `field_definitions = []`
- WHEN the modal is submitted
- THEN `custom_fields = {}` is passed to create_ticket_channel
