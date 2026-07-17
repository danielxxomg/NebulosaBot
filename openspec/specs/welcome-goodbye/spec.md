# Welcome/Goodbye Specification

## Purpose

Generate and dispatch welcome/goodbye greeting cards on member join and leave events.

## Requirements

### Requirement: Localized greeting card text

The system MUST render greeting card title and member-count text in the guild's configured language by receiving pre-translated strings from the caller. Card generation MUST NOT contain hardcoded greeting copy. Spanish (`es`) and English (`en`) outputs MUST be independently testable.

#### Scenario: Spanish welcome card

- GIVEN a guild configured with language `es` and welcome card enabled
- WHEN a member joins and the card is generated
- THEN the title uses the Spanish welcome string and the count uses the Spanish member-count string with the member number interpolated

#### Scenario: English goodbye card

- GIVEN a guild configured with language `en` and goodbye card enabled
- WHEN a member leaves and the card is generated
- THEN the title uses the English goodbye string and the count uses the English member-count string

#### Scenario: Caller passes translated strings

- GIVEN `GreetingService` resolves the guild language via `t()`
- WHEN `generate_greeting_card()` is invoked
- THEN the rendered card uses the `greeting_title` and `member_count_text` arguments supplied by the caller, not hardcoded English

#### Scenario: Test commands render localized cards

- GIVEN an admin invokes `/welcome test` or `/goodbye test` in a Spanish guild
- WHEN the test card is generated
- THEN the card renders with the same localized strings as a live join/leave event

### Requirement: Branded banner identity treatment

The system MUST render greeting cards as a premium branded banner carrying guild identity (guild icon), member display name, member avatar, and member count. The banner carries greeting and identity only; a brief call-to-action lives in the message content, not on the banner.

#### Scenario: Guild icon present

- GIVEN a guild with a configured icon asset
- WHEN a greeting card is generated with the guild icon input
- THEN the rendered banner includes the guild icon as identity treatment

#### Scenario: Missing guild icon fallback

- GIVEN a guild with a null or unset guild icon
- WHEN a greeting card is generated
- THEN an elegant non-breaking fallback is used (no raised error) and the banner still renders with greeting text, avatar, and member count

#### Scenario: Avatar fetch failure fallback

- GIVEN the member avatar asset cannot be fetched or decoded
- WHEN a greeting card is generated
- THEN a default placeholder avatar is rendered and delivery proceeds without error

### Requirement: Welcome onboarding call-to-action

The system MUST append a brief welcome call-to-action to the welcome message content pointing to the configured onboarding/start channel when one is set. The CTA MUST remain visible even when an administrator has configured a custom welcome message. The CTA MUST be omitted without breaking delivery when no onboarding channel is configured or the channel is inaccessible.

#### Scenario: Default welcome with CTA

- GIVEN welcome enabled, an onboarding channel configured, and no custom welcome message
- WHEN a member joins
- THEN the welcome message content includes the CTA mentioning the onboarding channel

#### Scenario: Custom message preserves CTA

- GIVEN welcome enabled, an onboarding channel configured, and a custom welcome message set
- WHEN a member joins
- THEN the content contains the formatted custom message AND the CTA is still present

#### Scenario: No onboarding channel omits CTA safely

- GIVEN welcome enabled and no onboarding channel configured
- WHEN a member joins
- THEN no CTA is appended and the welcome card/message is still delivered

#### Scenario: Inaccessible onboarding channel omits CTA safely

- GIVEN welcome enabled and the configured onboarding channel is not resolvable in the guild
- WHEN a member joins
- THEN no CTA is appended and delivery still succeeds

#### Scenario: Goodbye has no CTA

- GIVEN goodbye enabled and an onboarding channel configured
- WHEN a member leaves
- THEN the goodbye message contains no onboarding CTA

### Requirement: Welcome card on join

The system MUST send a welcome card to `welcome_channel_id` when `welcome_card_enabled` is true, with card text localized to the guild's configured language and the message carrying the onboarding CTA per the welcome onboarding call-to-action requirement.

#### Scenario: Member joins guild

- GIVEN `welcome_card_enabled` is true and `welcome_channel_id` is set
- WHEN a member joins the guild
- THEN a localized welcome card image is generated and sent to the welcome channel with the onboarding CTA in the message content when configured

#### Scenario: Welcome disabled

- GIVEN `welcome_card_enabled` is false
- WHEN a member joins the guild
- THEN no welcome card is sent

### Requirement: Goodbye card on leave

The system MUST send a goodbye card to `goodbye_channel_id` when `goodbye_card_enabled` is true, with card text localized to the guild's configured language. Goodbye messages MUST NOT include an onboarding CTA.

#### Scenario: Member leaves guild

- GIVEN `goodbye_card_enabled` is true and `goodbye_channel_id` is set
- WHEN a member leaves the guild
- THEN a localized goodbye card image is generated and sent to the goodbye channel with no onboarding CTA

### Requirement: Card generation

The system MUST generate greeting cards using a pure Pillow renderer that receives pre-translated `greeting_title` and `member_count_text` strings plus identity inputs (member avatar, username, guild name, guild icon, member count). The renderer MUST NOT resolve translations itself. The greeting title and member-count text MUST reflect the guild's configured language. A nullable guild icon and an avatar-fetch failure MUST each use a non-breaking fallback so the card still renders.

#### Scenario: Generate welcome card

- GIVEN a member and guild
- WHEN `generate_greeting_card()` is invoked with type `welcome`, a translated `greeting_title`, and a translated `member_count_text`
- THEN the returned image contains the gradient background, circular avatar, guild identity treatment, and the supplied localized greeting and count text

#### Scenario: Missing avatar

- GIVEN a member has no avatar
- WHEN the card is generated
- THEN a default placeholder avatar is rendered and the card still contains localized title and count text

#### Scenario: Missing guild icon

- GIVEN the guild has no usable guild icon asset
- WHEN the card is generated
- THEN a non-breaking fallback is used and the card still renders with avatar, localized title, and member count

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
