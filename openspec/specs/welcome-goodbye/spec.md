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

The system MUST ship a `PillowGreetingRenderer` implementing `GreetingRenderer` as the default for both the default and `gaming_neon` themes. Rendering MUST use the brand tokens from `bot/utils/brand.py` (default accent `brand.ACCENT`, neon accents `brand.ACCENT_A`/`brand.ACCENT_B`) and MUST NOT hardcode `#7289da`, `#FF2E97`, `#00E5FF`, or any hex literal. The renderer MUST run in a worker thread via `asyncio.to_thread` so the event loop is never blocked.
(Previously: `PillowGreetingRenderer` was the Cycle 1 default for the single default theme; the neon theme branch did not exist.)

#### Scenario: Default render uses brand tokens

- GIVEN `PillowGreetingRenderer` is the injected default and `theme_id` is null
- WHEN a greeting card is rendered
- THEN the accent color is read from `bot/utils/brand.py` (`brand.ACCENT`) and no hex literal appears in the renderer source

#### Scenario: Neon render uses neon brand tokens

- GIVEN `PillowGreetingRenderer` is the injected default and `theme_id = "gaming_neon"`
- WHEN a greeting card is rendered
- THEN the accents are read from `brand.ACCENT_A`/`brand.ACCENT_B` and no hex literal appears in the renderer source

#### Scenario: Render runs off the event loop

- GIVEN a greeting dispatch is in flight (default or neon)
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

### Requirement: Setup-module configuration parity and preview

Welcome and goodbye configuration MUST be fully manageable through the `/setup` panel modules, producing the SAME persisted state and cache invalidation as the deleted command groups. Each module MUST provide a test button that renders and delivers a REAL preview (localized card + message content) to the configured channel. Preview delivery failures (missing/inaccessible channel) MUST surface an ephemeral panel error without mutating config.

#### Scenario: Module save matches legacy command effect

- GIVEN the Welcome module sets channel #general and enables welcome
- WHEN the admin saves
- THEN `welcome_channel_id` is updated AND the cache entry is invalidated exactly as the old `/welcome channel` command did

#### Scenario: Test button sends real preview

- GIVEN a guild with language `es` and a welcome channel configured
- WHEN the admin presses the Welcome test button
- THEN a real Spanish welcome card is delivered to the configured channel

#### Scenario: Preview failure is ephemeral and safe

- GIVEN no welcome channel is configured
- WHEN the test button is pressed
- THEN an ephemeral error explains the missing channel and no message is sent anywhere


<!-- BEGIN DELTA: welcome-neon-timer-banana (welcome-goodbye) -->

## ADDED Requirements
### Requirement: Neon theme rendered procedurally via Pillow

The system MUST render the `gaming_neon` theme in `PillowGreetingRenderer`
using procedural Pillow calls: a hexagonal polygon, a glow via
`ImageFilter.GaussianBlur`, and a magenta→cyan diagonal using `brand.ACCENT_A`
(`0xFF2E97`) → `brand.ACCENT_B` (`0x00E5FF`). The neon branch MUST read both
accent colors from `bot/utils/brand.py` and MUST NOT hardcode `#FF2E97`,
`#00E5FF`, or any hex literal. The renderer MUST run off the event loop via
`asyncio.to_thread` (Pillow blocks; the event loop MUST NOT be blocked). The
neon theme MUST produce PNG bytes (TDD-asserted) for both `welcome` and
`goodbye`.

#### Scenario: Neon welcome card renders with neon accents

- GIVEN a guild with `theme_id = "gaming_neon"` and welcome card enabled
- WHEN a member joins and `PillowGreetingRenderer.render(..., theme_id="gaming_neon")` runs
- THEN the returned PNG uses `brand.ACCENT_A` and `brand.ACCENT_B` (magenta→cyan) and no hex literal appears in the renderer source

#### Scenario: Neon render runs off the event loop

- GIVEN a neon greeting dispatch is in flight
- WHEN `dispatch_greeting` calls the renderer with `theme_id="gaming_neon"`
- THEN the call is wrapped in `asyncio.to_thread` and the event loop is not blocked

#### Scenario: Neon glow uses GaussianBlur not SVG filter

- GIVEN the neon theme is rendered on `python:3.11-slim` (no libcairo)
- WHEN the neon glow effect is applied
- THEN the glow is produced via `ImageFilter.GaussianBlur` (Pillow) and the cairosvg/SVG path is NOT required

### Requirement: GreetingRenderer interface accepts theme_id

The `GreetingRenderer` interface MUST accept an optional `theme_id: str | None`
parameter on `render()` that selects the theme, defaulting to the existing
default theme when `None` or unrecognised. The interface MUST NOT resolve
translations (unchanged from Cycle 1). `GreetingService` MUST pass the guild's
configured `theme_id` from `GreetingConfig` to the renderer; when the config
`theme_id` is null, the default theme MUST render. The interface signature
change MUST be backwards-compatible: existing callers omitting `theme_id`
MUST render the default theme unchanged.

#### Scenario: Interface accepts theme_id and stays translation-free

- GIVEN the `GreetingRenderer` protocol after the change
- WHEN `render(...)` is invoked with `theme_id="gaming_neon"`
- THEN the signature accepts `theme_id` and MUST NOT call `t()` or any translator

#### Scenario: Default theme renders when theme_id is null

- GIVEN a guild whose `GreetingConfig.theme_id` is null
- WHEN `dispatch_greeting` calls the renderer
- THEN the renderer receives `theme_id=None` (or omits it) and the default theme renders exactly as Cycle 1

#### Scenario: Unknown theme_id falls back to default

- GIVEN a guild whose `theme_id` is an unrecognised value
- WHEN the renderer is invoked
- THEN the default theme renders (no raise, no broken card)

### Requirement: Neon theme is Pillow-default and SVG stays gated

Because `python:3.11-slim` (Pterodactyl) ships no `libcairo`, the neon theme
MUST be delivered via Pillow procedural rendering (no new system dependency).
The cairosvg/SVG path MUST remain behind the existing boot probe
(`bot/bot.py:220-243`) and MUST NOT be enabled for the neon theme in Cycle 2.
When the probe succeeds, the Cycle 2 default MUST still be
`PillowGreetingRenderer` (Pillow procedural, including neon) so neon never
depends on libcairo. The probe result remains a single injection decision.

#### Scenario: Neon renders with Pillow even when cairosvg present

- GIVEN the cairosvg import probe succeeds (libcairo available)
- WHEN the Cycle 2 injector selects a renderer and a `gaming_neon` card is requested
- THEN `PillowGreetingRenderer` is still injected and the neon theme renders procedurally (the SVG path is NOT used for neon in Cycle 2)

#### Scenario: Neon renders with Pillow when cairosvg absent

- GIVEN `libcairo` is not available and the cairosvg probe raises `ImportError`
- WHEN the bot boots and a `gaming_neon` card is requested
- THEN `PillowGreetingRenderer` is injected, a WARNING is logged, and the neon theme renders procedurally
<!-- END DELTA: welcome-neon-timer-banana (welcome-goodbye) -->

<!-- BEGIN DELTA: ops-zero-lite (welcome-goodbye) -->
## ADDED Requirements

### Requirement: Raid-bounded dispatch (Semaphore + drop) [PRESERVED]

The system MUST preserve the shipped per-guild bound in `GreetingService.dispatch_greeting` (verified: `bot/services/greeting_service.py:31 RAID_MAX_CONCURRENT=2 "(D4 raid guard)"`, `:57 _raid_semaphores: dict[str, Semaphore]`, `:200-201 locked() guard + WARNING "greeting dropped: raid saturation guild=%s"` then `async with sem`, `:214 asyncio.to_thread(render_fn, ...)`; `evict_guild_sync` at `:101`). Acquisition MUST be non-blocking drop (not queue); 100 concurrent joins MUST NOT produce 100 concurrent `to_thread` renders. Regression guard: `tests/test_greeting_service_raid.py::test_semaphore_is_guild_scoped` and `test_burst_caps_concurrency_and_drops_excess` (peak 2, drops=4) MUST stay green.

#### Scenario: Concurrent burst is bounded

- GIVEN 100 `on_member_join` events fire concurrently for guild G
- WHEN `dispatch_greeting` runs
- THEN at most 2 renders execute concurrently per guild; excess drop with WARNING

#### Scenario: Saturation drops do not error

- GIVEN semaphore for G is saturated (2 slots held)
- WHEN another `dispatch_welcome` arrives
- THEN it returns early without exception and without enqueue

#### Scenario: Render still off event loop

- GIVEN a welcome dispatch proceeds (slot acquired)
- WHEN renderer is invoked
- THEN call is wrapped in `asyncio.to_thread` and Pillow does not block loop

#### Scenario: Eviction on guild leave

- GIVEN a guild semaphore exists in `_raid_semaphores`
- WHEN `GreetingService.evict_guild_sync(guild_id)` runs via `on_guild_remove`
- THEN entry is removed (no RAM leak)

<!-- END DELTA: ops-zero-lite (welcome-goodbye) -->
