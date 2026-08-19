# Ticket Commands Specification

## Purpose

Define slash commands for ticket panel deployment and ticket category management.

## Requirements

### Requirement: Ticket panel command

The system MUST provide a `/ticket_panel` command to deploy the ticket panel in the current channel. The command MUST be restricted via `@app_commands.default_permissions(administrator=True)`. Responses MUST be ephemeral.

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

#### Scenario: List categories

- GIVEN a guild with ticket categories
- WHEN `/list_categories` is invoked
- THEN an ephemeral embed lists all categories ordered by their guild-scoped order

### Requirement: Delete category command

The system MUST provide a `/delete_category` command to remove a ticket category. The command MUST be restricted via `@app_commands.default_permissions(administrator=True)`. Responses MUST be ephemeral.

#### Scenario: Delete existing category

- GIVEN an existing ticket category with no open tickets
- WHEN `/delete_category` targets it
- THEN the category is removed from the database
- AND the confirmation is visible only to the invoking user

#### Scenario: Delete with open tickets

- GIVEN a ticket category with open tickets
- WHEN `/delete_category` targets it
- THEN the command is rejected to prevent orphaning active tickets (ephemeral)

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

<!-- BEGIN DELTA: ticket-physical-split S3 -->

### Requirement: Flow-aligned cog split with stable registration

The ticket cog MUST be physically split into administration, lifecycle, notes, and integrity flow modules behind a stable `TicketsCog` facade. Hybrid command names, command permissions, interaction responses, listeners, background tasks, and `async def setup(bot)` registration MUST remain compatible.

#### Scenario: Command registration survives extraction

- GIVEN the bot loads the ticket extension after the split
- WHEN `setup(bot)` executes
- THEN the same hybrid commands and listeners are registered exactly once

#### Scenario: Existing command behavior survives extraction

- GIVEN an administrator or moderator invokes an existing ticket command
- WHEN the command is handled by its extracted flow module
- THEN its permission result, guild-scoped response, and service call remain unchanged

### Requirement: Guild-scoped command database boundary

Every direct database lookup retained or moved from `TicketsCog` MUST carry the invoking guild ID or delegate to a service method that enforces ownership before disclosure or mutation. The former sub-ticket, transfer, and category-edit callers at `tickets.py:568`, `tickets.py:685`, and `tickets.py:722` MUST have no guild-scope gap; all 14 direct `self.bot.db` references MUST receive the same audit.

#### Scenario: Deferred caller gaps are closed

- GIVEN a command resolves a ticket by channel before sub-ticket creation, transfer, or category edit
- WHEN the lookup runs in guild A
- THEN only the guild A ticket is eligible and another guild's row is neither returned nor changed

#### Scenario: Cross-guild command input is denied

- GIVEN a command receives a ticket or channel identifier owned by guild B
- WHEN a guild A actor invokes the command
- THEN the command returns a safe denial/error and performs no guild B mutation

### Requirement: S3 guardrail gate

The command split MUST NOT be accepted as complete until the complete S3 gate is green: `uv run pytest` reports the 1,864-pass/5-skip baseline or an approved equivalent, `uv run mypy bot` and `uv run mypy tests` report zero errors, `uv run ruff check bot tests scripts` reports zero findings including all 11 baseline `scripts/` findings, the `GUILD_SCOPE_GAPS` ledger is empty, and permission, live-schema, DDL, service, cog, and view contracts pass.

#### Scenario: Guardrail failure blocks completion

- GIVEN any guild gap, Ruff finding, type error, failed contract, or incomplete live/DDL gate remains
- WHEN S3 completion is evaluated
- THEN the change remains incomplete and no downstream slice is considered green

<!-- END DELTA: ticket-physical-split S3 -->
