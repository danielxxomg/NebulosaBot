# Welcome/Goodbye Specification

## Purpose

Generate and dispatch welcome/goodbye greeting cards on member join and leave events.

## Requirements

### Requirement: Welcome card on join

The system MUST send a welcome card to `welcome_channel_id` when `welcome_card_enabled` is true.

#### Scenario: Member joins guild

- GIVEN `welcome_card_enabled` is true and `welcome_channel_id` is set
- WHEN a member joins the guild
- THEN a welcome card image is generated and sent to the welcome channel

#### Scenario: Welcome disabled

- GIVEN `welcome_card_enabled` is false
- WHEN a member joins the guild
- THEN no welcome card is sent

### Requirement: Goodbye card on leave

The system MUST send a goodbye card to `goodbye_channel_id` when `goodbye_card_enabled` is true.

#### Scenario: Member leaves guild

- GIVEN `goodbye_card_enabled` is true and `goodbye_channel_id` is set
- WHEN a member leaves the guild
- THEN a goodbye card image is generated and sent to the goodbye channel

### Requirement: Card generation

The system MUST generate greeting cards using `ImageService.generate_greeting_card()` with the dark gradient style, member avatar, username, and guild name.

#### Scenario: Generate welcome card

- GIVEN a member and guild
- WHEN `generate_greeting_card()` is invoked with type `welcome`
- THEN the returned image contains the dark gradient background, circular avatar, and greeting text

#### Scenario: Missing avatar

- GIVEN a member has no avatar
- WHEN the card is generated
- THEN a default placeholder avatar is rendered

### Requirement: Missing channel guard

The system MUST skip sending a greeting card when the configured channel is null or inaccessible.

#### Scenario: Welcome channel missing

- GIVEN `welcome_channel_id` is null
- WHEN a member joins the guild
- THEN no card is sent and no error is surfaced

### Requirement: Welcome config command group

The system MUST provide a `/welcome` hybrid command group with subcommands: `config` (show current settings), `channel` (set welcome channel), `toggle` (enable/disable welcome), and `message` (set template). All subcommands MUST be admin-gated via `@app_commands.default_permissions(administrator=True)`.

#### Scenario: Show welcome config

- GIVEN an admin invokes `/welcome config`
- WHEN the command executes
- THEN an ephemeral embed displays current welcome channel, toggle state, and message template

#### Scenario: Set welcome channel

- GIVEN an admin invokes `/welcome channel #general`
- WHEN the command executes
- THEN the welcome channel is updated to #general and the cache is invalidated

#### Scenario: Toggle welcome off

- GIVEN welcome is currently enabled
- WHEN an admin invokes `/welcome toggle`
- THEN welcome is disabled and a confirmation is shown

#### Scenario: Set welcome message template

- GIVEN an admin invokes `/welcome message Welcome {user} to {server}!`
- WHEN the command executes
- THEN the welcome message template is saved and cache invalidated

#### Scenario: Non-admin blocked

- GIVEN a non-admin user
- WHEN they invoke `/welcome config`
- THEN Discord blocks the command (permission hint)

### Requirement: Goodbye config command group

The system MUST provide a `/goodbye` hybrid command group with subcommands: `config` (show current settings), `channel` (set goodbye channel), `toggle` (enable/disable goodbye), and `message` (set template). All subcommands MUST be admin-gated via `@app_commands.default_permissions(administrator=True)`.

#### Scenario: Show goodbye config

- GIVEN an admin invokes `/goodbye config`
- WHEN the command executes
- THEN an ephemeral embed displays current goodbye channel, toggle state, and message template

#### Scenario: Set goodbye channel

- GIVEN an admin invokes `/goodbye channel #goodbye`
- WHEN the command executes
- THEN the goodbye channel is updated and cache invalidated

#### Scenario: Toggle goodbye off

- GIVEN goodbye is currently enabled
- WHEN an admin invokes `/goodbye toggle`
- THEN goodbye is disabled and a confirmation is shown

#### Scenario: Set goodbye message template

- GIVEN an admin invokes `/goodbye message Goodbye {user}!`
- WHEN the command executes
- THEN the goodbye message template is saved and cache invalidated

#### Scenario: Non-admin blocked

- GIVEN a non-admin user
- WHEN they invoke `/goodbye config`
- THEN Discord blocks the command (permission hint)
