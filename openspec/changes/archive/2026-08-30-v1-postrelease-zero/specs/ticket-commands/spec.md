# Delta for ticket-commands

## MODIFIED Requirements

### Requirement: Flow-aligned cog split with stable registration

The ticket cog MUST be physically split into administration, lifecycle, notes, and integrity flow modules behind a stable `TicketsCog` facade. Slash command names (`/ticket_panel`, `/create_category`, etc. via `@app_commands.command()`; no `hybrid_command`), command permissions, interaction responses (`t()`), listeners, background tasks, and `async def setup(bot)` registration MUST remain compatible. Prefix invocations MUST remain inert (`get_prefix -> []`).

(Previously: described as hybrid command names)

#### Scenario: Command registration survives extraction

- GIVEN the bot loads the ticket extension after the split
- WHEN `setup(bot)` executes
- THEN the same slash commands and listeners are registered exactly once

#### Scenario: Existing command behavior survives extraction

- GIVEN an administrator or moderator invokes an existing ticket command via slash
- WHEN the command is handled by its extracted flow module
- THEN its permission result, guild-scoped response via `t()`, and service call remain unchanged

### Requirement: Ticket panel command

The system MUST provide a slash-only `/ticket_panel` command via `@app_commands.command()` (no hybrid) to deploy the ticket panel in the current channel. The command MUST be restricted via `@app_commands.default_permissions(administrator=True)` and MUST use `t()` for responses. Prefix inert. Responses MUST be ephemeral.

(Previously: implicitly allowed hybrid; now explicitly slash-only)

#### Scenario: Deploy panel

- GIVEN an administrator in a text channel
- WHEN `/ticket_panel` is invoked via slash
- THEN the ticket panel message is sent and its IDs are persisted to the guild config and the confirmation is visible only to the invoking user via `t()`

#### Scenario: Insufficient permissions

- GIVEN a regular user
- WHEN `/ticket_panel` is invoked via slash
- THEN the command is rejected with a permission error via `t()`

### Requirement: Create category command

The system MUST provide a slash-only `/create_category` command via `@app_commands.command()` to add a ticket category. The command MUST be restricted via `@app_commands.default_permissions(administrator=True)` and use `t()`. Prefix inert. Responses MUST be ephemeral.

(Previously: implicitly hybrid)

#### Scenario: Create category

- GIVEN an administrator invokes `/create_category` via slash with a name
- WHEN it executes
- THEN a new TicketCategory is inserted with guild-scoped ordering and confirmation via `t()`

#### Scenario: Duplicate name

- GIVEN a category named "Support" already exists in the guild
- WHEN `/create_category` creates another "Support" via slash
- THEN the command is rejected with a duplicate name error ephemerally via `t()`

### Requirement: Delete category command

The system MUST provide a slash-only `/delete_category` command via `@app_commands.command()` to remove a ticket category. The command MUST be restricted via `@app_commands.default_permissions(administrator=True)` and `@is_admin()` guard, with ephemeral responses via `t()`. Prefix inert.

(Previously: hybrid; guard was `@is_mod()` then `@is_admin()` but still dual path)

#### Scenario: Delete existing category

- GIVEN an existing ticket category with no open tickets
- WHEN `/delete_category` targets it via slash
- THEN the category is removed from the database and confirmation via `t()` is visible only to the invoker

#### Scenario: Delete with open tickets

- GIVEN a ticket category with open tickets
- WHEN `/delete_category` targets it via slash
- THEN the command is rejected ephemerally via `t()` to prevent orphaning active tickets
