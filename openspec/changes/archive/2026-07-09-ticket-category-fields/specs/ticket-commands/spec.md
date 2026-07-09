# Delta for Ticket Commands

## ADDED Requirements

### Requirement: Configure fields command

The system MUST provide a `/configure_fields` command to set `field_definitions` on an existing ticket category. The command MUST accept `category_id` (required) and `fields_json` (required, a JSON string). The command MUST be restricted via `@app_commands.default_permissions(administrator=True)`. Responses MUST be ephemeral.

#### Scenario: Configure fields on category

- GIVEN an administrator and a category with id "abc"
- WHEN `/configure_fields category_id:abc fields_json:'[{"key":"player_nick","label":"Player Nickname","style":"short","required":true}]'` is invoked
- THEN the category's `field_definitions` is updated and a confirmation is shown

#### Scenario: Invalid JSON rejected

- GIVEN an administrator
- WHEN `/configure_fields` is invoked with `fields_json: 'not-json'`
- THEN an ephemeral error message indicates invalid JSON

#### Scenario: More than 3 fields rejected

- GIVEN an administrator
- WHEN `/configure_fields` is invoked with 4 field definitions
- THEN an ephemeral error message indicates max 3 fields

#### Scenario: Missing key or label rejected

- GIVEN an administrator
- WHEN `/configure_fields` is invoked with a field missing `label`
- THEN an ephemeral error message indicates the missing required property

#### Scenario: Invalid style rejected

- GIVEN an administrator
- WHEN `/configure_fields` is invoked with `style: "dropdown"`
- THEN an ephemeral error message indicates style must be "short" or "paragraph"

#### Scenario: Non-existent category rejected

- GIVEN an administrator
- WHEN `/configure_fields` is invoked with a non-existent category id
- THEN an ephemeral error message indicates the category was not found

#### Scenario: Insufficient permissions

- GIVEN a regular user
- WHEN `/configure_fields` is invoked
- THEN the command is rejected with a permission error
