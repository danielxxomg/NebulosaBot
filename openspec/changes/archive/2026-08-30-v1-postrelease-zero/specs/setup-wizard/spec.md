# Delta for setup-wizard

## MODIFIED Requirements

### Requirement: Setup command

The system MUST provide a slash-only `/setup` command via `@app_commands.command()` (MUST NOT use `hybrid_command`; prefix inert via `get_prefix -> []`) with no parameters gated to administrators (`@app_commands.default_permissions(administrator=True)` and `@is_admin()`), that opens the persistent setup panel defined by the `setup-panel` capability. The command takes NO Discord-object parameters; all configuration flows through guided panel editors. Responses MUST use `t()`.

(Previously: purpose described as `/setup` hybrid command; requirement already said pure app command but purpose and legacy docs implied hybrid)

#### Scenario: Admin opens the panel

- GIVEN an administrator in any guild
- WHEN `/setup` is invoked via slash with no arguments
- THEN the persistent non-ephemeral panel message is posted and no guild field is changed by invocation alone

#### Scenario: Non-admin rejected

- GIVEN a regular user
- WHEN `/setup` is invoked via slash
- THEN the command is blocked/rejected as a permission error via `t()` ephemerally

#### Scenario: No parameter surface remains

- GIVEN the deployed slash tree
- WHEN the `/setup` command signature is inspected
- THEN it declares zero parameters and is not a hybrid declaration

#### Scenario: Prefix inert

- GIVEN a user sends `nb!setup` as text
- WHEN the message is processed
- THEN no command is invoked

### Requirement: Internationalization

All `/setup` response strings MUST use the `t(guild_id, key)` function and exist in both `en.json` and `es.json`. No hardcoded user-facing strings.

#### Scenario: Response in guild language

- GIVEN a guild configured with `language=en`
- WHEN `/setup` completes successfully via slash
- THEN the confirmation embed text is in English via `t()`

#### Scenario: Response in Spanish

- GIVEN a guild configured with `language=es`
- WHEN `/setup` completes successfully via slash
- THEN the confirmation embed text is in Spanish via `t()`
