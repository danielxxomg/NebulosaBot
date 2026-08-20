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

### Requirement: GreetingRenderer interface

The system MUST define a `GreetingRenderer` protocol/interface that accepts
identity inputs plus pre-translated `greeting_title` and `member_count_text`
strings and returns a PNG image. The interface MUST NOT resolve translations.
`GreetingService` MUST depend on the interface, not on a concrete renderer, so
Cycle 2 can swap the implementation in one injection line.

#### Scenario: Service depends on the interface

- GIVEN `GreetingRenderer` is defined as a protocol
- WHEN `GreetingService` is constructed at `bot/bot.py:215`
- THEN it receives a `GreetingRenderer` instance and holds it as the interface type

#### Scenario: Interface receives translated strings only

- GIVEN a `GreetingRenderer` implementation
- WHEN `render(...)` is invoked
- THEN the signature accepts `greeting_title` and `member_count_text` and MUST NOT call `t()` or any translator

### Requirement: Pillow is the default renderer

The system MUST ship a `PillowGreetingRenderer` implementing `GreetingRenderer`
as the Cycle 1 default. Rendering MUST use the brand tokens from `bot/utils/brand.py`
and MUST NOT hardcode `#7289da` or any hex literal. The renderer MUST run in a
worker thread via `asyncio.to_thread` so the event loop is never blocked.

#### Scenario: Default render uses brand tokens

- GIVEN `PillowGreetingRenderer` is the injected default
- WHEN a greeting card is rendered
- THEN the accent color is read from `bot/utils/brand.py` and no hex literal appears in the renderer source

#### Scenario: Render runs off the event loop

- GIVEN a greeting dispatch is in flight
- WHEN `dispatch_greeting` calls the renderer
- THEN the call is wrapped in `asyncio.to_thread` and the event loop is not blocked

### Requirement: cairosvg probe with Pillow fallback

Because `python:3.11-slim` (Pterodactyl) ships no `libcairo`, the system MUST
probe for cairosvg availability at boot and fall back to `PillowGreetingRenderer`
when the probe fails. The fallback MUST be logged at WARNING and MUST NOT raise
or abort startup. The probe result MUST be a single injection decision so Cycle 2
can flip it in one line.

#### Scenario: cairosvg missing falls back to Pillow

- GIVEN `libcairo` is not available and the cairosvg import probe raises `ImportError`
- WHEN the bot boots
- THEN `PillowGreetingRenderer` is injected, a WARNING is logged, and startup proceeds without error

#### Scenario: cairosvg present keeps Pillow default in Cycle 1

- GIVEN the cairosvg import probe succeeds
- WHEN the Cycle 1 injector selects a renderer
- THEN `PillowGreetingRenderer` is still injected (Cycle 1 default) and the cairosvg path is reserved for Cycle 2

### Requirement: Branded banner identity treatment

The system MUST render greeting cards as a premium branded banner carrying
guild identity (guild icon), member display name, member avatar, and member
count, using the Nebulosa brand tokens from `bot/utils/brand.py` as the accent
source. The banner carries greeting and identity only; a brief call-to-action
lives in the message content, not on the banner.

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

The system MUST generate greeting cards through the `GreetingRenderer`
interface using a Pillow-default implementation that receives pre-translated
`greeting_title` and `member_count_text` strings plus identity inputs (member
avatar, username, guild name, guild icon, member count). The renderer MUST
NOT resolve translations itself. The greeting title and member-count text MUST
reflect the guild's configured language. A nullable guild icon and an
avatar-fetch failure MUST each use a non-breaking fallback so the card still
renders. The renderer MUST run off the event loop via `asyncio.to_thread`.

#### Scenario: Generate welcome card

- GIVEN a member and guild
- WHEN `generate_greeting_card()` is invoked with type `welcome`, a translated `greeting_title`, and a translated `member_count_text`
- THEN the `GreetingRenderer` returns an image containing the gradient background, circular avatar, guild identity treatment, and the supplied localized greeting and count text

#### Scenario: Missing avatar

- GIVEN a member has no avatar
- WHEN the card is generated
- THEN a default placeholder avatar is rendered and the card still contains localized title and count text

#### Scenario: Missing guild icon

- GIVEN the guild has no usable guild icon asset
- WHEN the card is generated
- THEN a non-breaking fallback is used and the card still renders with avatar, localized title, and member count

#### Scenario: Render is dispatched to a worker thread

- GIVEN a greeting card is requested
- WHEN the renderer executes
- THEN the Pillow work runs in a thread via `asyncio.to_thread`, not on the event loop

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
