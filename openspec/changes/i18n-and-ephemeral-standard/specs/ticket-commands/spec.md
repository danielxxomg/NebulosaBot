# Delta for Ticket Commands

## MODIFIED Requirements

### Requirement: Ticket panel command

The system MUST provide a `/ticket_panel` command to deploy the ticket panel in the current channel. The command MUST be restricted via `@app_commands.default_permissions(administrator=True)`. Responses MUST be ephemeral.

(Previously: No default_permissions decorator, responses were permanent)

#### Scenario: Deploy panel

- GIVEN an administrator in a text channel
- WHEN `/ticket_panel` is invoked
- THEN the ticket panel message is sent and its IDs are persisted to the guild config
- AND the confirmation is visible only to the invoking user

#### Scenario: Insufficient permissions

- GIVEN a regular user
- WHEN `/ticket_panel` is invoked
- THEN the command is rejected with a permission error

### Requirement: Create category command

The system MUST provide a `/create_category` command to add a ticket category. The command MUST be restricted via `@app_commands.default_permissions(administrator=True)`. Responses MUST be ephemeral.

(Previously: No default_permissions decorator, responses were permanent)

#### Scenario: Create category

- GIVEN an administrator
- WHEN `/create_category` is invoked with a name and optional description
- THEN a new TicketCategory is inserted with guild-scoped ordering
- AND the confirmation is visible only to the invoking user

#### Scenario: Duplicate name

- GIVEN a category named "Support" already exists in the guild
- WHEN `/create_category` creates another "Support"
- THEN the command is rejected with a duplicate name error (ephemeral)

### Requirement: List categories command

The system MUST provide a `/list_categories` command to display configured categories. The command MUST be restricted via `@app_commands.default_permissions(administrator=True)`. Responses MUST be ephemeral.

(Previously: No default_permissions decorator, responses were permanent)

#### Scenario: List categories

- GIVEN a guild with ticket categories
- WHEN `/list_categories` is invoked
- THEN an ephemeral embed lists all categories ordered by their guild-scoped order

### Requirement: Delete category command

The system MUST provide a `/delete_category` command to remove a ticket category. The command MUST be restricted via `@app_commands.default_permissions(administrator=True)`. Responses MUST be ephemeral.

(Previously: No default_permissions decorator, responses were permanent)

#### Scenario: Delete existing category

- GIVEN an existing ticket category with no open tickets
- WHEN `/delete_category` targets it
- THEN the category is removed from the database
- AND the confirmation is visible only to the invoking user

#### Scenario: Delete with open tickets

- GIVEN a ticket category with open tickets
- WHEN `/delete_category` targets it
- THEN the command is rejected to prevent orphaning active tickets (ephemeral)
