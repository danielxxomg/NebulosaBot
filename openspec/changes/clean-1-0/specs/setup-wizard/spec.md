# Delta for Setup Wizard

## MODIFIED Requirements

### Requirement: Setup command

The system MUST provide a `/setup` pure app command (no parameters) gated to administrators that opens the persistent setup panel defined by the `setup-panel` capability. The command takes NO Discord-object parameters; all configuration flows through guided panel editors.

(Previously: `/setup` was a hybrid command with `ticket_category` required plus optional `mod_role`, `log_channel`, `language` params saved directly.)

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

## REMOVED Requirements

### Requirement: Required parameter — ticket_category

(Reason: category management moves into the setup panel's Tickets module via guided object selection — no raw parameter typing.)
(Migration: use `/setup` → Tickets module → create/select ticket category.)

### Requirement: Optional parameters

(Reason: `mod_role`, `log_channel`, and `language` editing move into the setup panel modules; partial-update semantics are preserved by per-field editors.)
(Migration: use the corresponding `/setup` module fields; omitted fields continue to retain existing values.)
