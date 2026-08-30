# Setup Wizard Specification

## Purpose

Define the `/setup` hybrid command that allows guild administrators to configure essential bot settings — especially `ticket_category_id` — without leaving Discord.

## Requirements

### Requirement: Setup command

The system MUST provide a `/setup` pure app command (no parameters) gated to administrators that opens the persistent setup panel defined by the `setup-panel` capability. The command takes NO Discord-object parameters; all configuration flows through guided panel editors.

#### Scenario: Admin opens the panel

- GIVEN an administrator in any guild
- WHEN `/setup` is invoked with no arguments
- THEN the persistent non-ephemeral panel message is posted and no guild field is changed by invocation alone

#### Scenario: Non-admin rejected

- GIVEN a regular user
- WHEN `/setup` is invoked
- THEN the command is blocked/rejected as a permission error

#### Scenario: No parameter surface remains

- GIVEN the deployed slash tree
- WHEN the `/setup` command signature is inspected
- THEN it declares zero parameters

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
