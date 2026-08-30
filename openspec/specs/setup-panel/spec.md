# Setup Panel Specification

## Purpose

Define the persistent `/setup` panel: one non-ephemeral message with Select-based module navigation replacing raw-parameter config commands. No raw UUIDs or JSON anywhere.

## Requirements

### Requirement: Persistent non-ephemeral panel

The system MUST provide a `/setup` pure app command posting ONE non-ephemeral panel message (persistent views survive restarts only on non-ephemeral messages). Navigation/actions MUST edit that same message in place — never post duplicates. A 🗑 button MUST delete it. The view MUST use static `custom_id`s registered via `bot.add_view()` in `setup_hook`.

#### Scenario: Panel opens as a real message

- GIVEN an administrator invokes `/setup`
- WHEN it executes
- THEN exactly one non-ephemeral panel message is posted (not ephemeral)

#### Scenario: Navigation edits in place

- GIVEN a panel exists
- WHEN the admin selects another module
- THEN the SAME message is edited; no new message appears

#### Scenario: Close button deletes panel

- GIVEN a panel exists
- WHEN anyone clicks 🗑
- THEN the panel message is deleted

#### Scenario: Panel survives restart

- GIVEN a panel predates a restart
- WHEN an admin clicks a component after restart
- THEN the static custom_id routes to the registered view and it responds normally

### Requirement: Module navigation with breadcrumb and refresh

The Select MUST list modules (`tickets`, `welcome`, `goodbye`, `log`, `language`). The body MUST show a breadcrumb of the current module and a refresh control re-reading state from service/cache before re-rendering.

#### Scenario: Breadcrumb reflects selection

- GIVEN the admin selects `welcome`
- WHEN the panel re-renders
- THEN the breadcrumb identifies `welcome`

#### Scenario: Refresh shows live state

- GIVEN another actor changed the welcome channel after render
- WHEN refresh is pressed
- THEN the panel shows the newly persisted value, not stale content

### Requirement: Authorization without new matrix key

`/setup` MUST carry `@app_commands.default_permissions(administrator=True)` (server admins may relax via Integrations). NO new permission-matrix key is created. Module mutations reuse existing keys via standard checks: `tickets.manage` gates Tickets-module actions; `greeting.manage` gates Welcome/Goodbye-module actions. In-module denials are ephemeral.

#### Scenario: Non-admin blocked by default

- GIVEN default Integrations
- WHEN a non-administrator attempts `/setup`
- THEN Discord blocks invocation with the permissions hint

#### Scenario: Module action denied without key

- GIVEN a relaxed-integration user without `tickets.manage`
- WHEN they trigger a Tickets-module mutation
- THEN an ephemeral denial replies and nothing changes

#### Scenario: Matrix grant authorizes module action

- GIVEN a relaxed-integration role holding `greeting.manage`
- WHEN that user saves a Welcome-module field
- THEN the change persists normally

### Requirement: Guided editors only — no raw UUID/JSON input

Every editor flow MUST use Selects, buttons, and modals over concrete Discord objects. No flow MAY require typing a snowflake ID, UUID, or JSON literal. The Tickets module MUST provide guided create-category, delete-category (confirmed), list-categories flows plus a custom-fields editor building the structure interactively.

#### Scenario: Category created via guided flow

- GIVEN the Tickets module
- WHEN an admin creates a category through the guided form
- THEN correct IDs persist, resolved from selected objects

#### Scenario: Custom fields edited without JSON

- GIVEN the custom-fields editor
- WHEN fields are added/edited/removed via form controls
- THEN the persisted structure updates correctly with no typed JSON

#### Scenario: Delete requires confirmation

- GIVEN a deletion request whose confirm dialog is not accepted
- THEN nothing is removed; on accept, the category is removed

### Requirement: Internationalization

All panel copy MUST resolve via `t(guild_id, "<key>")`; every key used MUST exist in both `bot/locales/es.json` and `bot/locales/en.json`.

#### Scenario: Spanish panel copy

- GIVEN language `es`
- WHEN the panel renders
- THEN labels/breadcrumbs are Spanish and the i18n key-coverage test passes
