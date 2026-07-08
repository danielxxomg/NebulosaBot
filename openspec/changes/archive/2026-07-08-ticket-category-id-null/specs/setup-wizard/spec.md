# Setup Wizard Specification

## Purpose

Define the `/setup` hybrid command that allows guild administrators to configure essential bot settings — especially `ticket_category_id` — without leaving Discord.

## Requirements

### Requirement: Setup command

The system MUST provide a `/setup` hybrid command gated by `@is_admin()` that configures guild settings.

#### Scenario: Admin runs setup with required param only

- GIVEN an administrator in a guild where `ticket_category_id` is null
- WHEN `/setup` is invoked with `ticket_category` (CategoryChannel) only
- THEN the guild's `ticket_category_id` is saved and other fields retain their current values

#### Scenario: Admin runs setup with all params

- GIVEN an administrator
- WHEN `/setup` is invoked with `ticket_category`, `mod_role`, `log_channel`, and `language`
- THEN all four fields are saved to the guild configuration

#### Scenario: Non-admin rejected

- GIVEN a regular user
- WHEN `/setup` is invoked
- THEN the command is rejected with a permission error

### Requirement: Required parameter — ticket_category

The `ticket_category` parameter SHALL be required and MUST be a valid `discord.CategoryChannel`.

#### Scenario: Valid category channel

- GIVEN a guild with an existing Discord category channel "Tickets"
- WHEN `/setup ticket_category:#Tickets` is invoked
- THEN the channel's Discord ID is saved as `ticket_category_id`

#### Scenario: Missing ticket_category

- GIVEN an administrator
- WHEN `/setup` is invoked without `ticket_category`
- THEN the command is rejected by Discord's parameter validation

### Requirement: Optional parameters

The parameters `mod_role` (Role), `log_channel` (TextChannel), and `language` (choice: `es|en`) SHALL be optional. When omitted, the system MUST preserve existing values.

#### Scenario: Partial update preserves existing

- GIVEN a guild with `mod_role_id=111` and `log_channel_id=222`
- WHEN `/setup ticket_category:#Tickets language:en` is invoked
- THEN `mod_role_id` remains `111` and `log_channel_id` remains `222`

#### Scenario: Language validation

- GIVEN an administrator
- WHEN `/setup ticket_category:#Tickets language:xx` is invoked
- THEN the command is rejected (invalid choice)

### Requirement: Internationalization

All `/setup` response strings MUST use the `t()` function and exist in both `en.json` and `es.json`.

#### Scenario: Response in guild language

- GIVEN a guild configured with `language=en`
- WHEN `/setup` completes successfully
- THEN the confirmation embed text is in English

#### Scenario: Response in Spanish

- GIVEN a guild configured with `language=es`
- WHEN `/setup` completes successfully
- THEN the confirmation embed text is in Spanish

### Requirement: Dashboard hint label

The dashboard config page MUST display "Discord Category Channel ID" instead of "UUID" as the label for the `ticket_category_id` field.

#### Scenario: Dashboard shows corrected label

- GIVEN an admin opens the dashboard guild config page
- WHEN the `ticket_category_id` hint is rendered
- THEN the label reads "Discord Category Channel ID (right-click → Copy Channel ID)"
