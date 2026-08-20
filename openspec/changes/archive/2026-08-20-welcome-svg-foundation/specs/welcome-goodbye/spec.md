# Delta for Welcome/Goodbye

Cycle 1 of 3. Introduces the `GreetingRenderer` interface with Pillow as the
default renderer, splits `ImageService` (SRP), and removes the untested compat
shim. Cycle 2 (Neon SVG via cairosvg/resvg) swaps the renderer in 1 line; it is
OUT OF SCOPE here.

## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Card generation

The system MUST generate greeting cards through the `GreetingRenderer`
interface using a Pillow-default implementation that receives pre-translated
`greeting_title` and `member_count_text` strings plus identity inputs (member
avatar, username, guild name, guild icon, member count). The renderer MUST
NOT resolve translations itself. The greeting title and member-count text MUST
reflect the guild's configured language. A nullable guild icon and an
avatar-fetch failure MUST each use a non-breaking fallback so the card still
renders. The renderer MUST run off the event loop via `asyncio.to_thread`.

(Previously: card generation lived inside a 454-line `ImageService` that also
owned rank cards; the greeting accent was hardcoded `#7289da`; rendering was
described as a "pure Pillow renderer" with no interface.)

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

### Requirement: Branded banner identity treatment

The system MUST render greeting cards as a premium branded banner carrying
guild identity (guild icon), member display name, member avatar, and member
count, using the Nebulosa brand tokens from `bot/utils/brand.py` as the accent
source. The banner carries greeting and identity only; a brief call-to-action
lives in the message content, not on the banner.

(Previously: the banner existed but its accent was the hardcoded Discord
blurple `#7289da`, bypassing brand tokens.)

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

## REMOVED Requirements

### Requirement: _generate_greeting_card_compatibly shim

(Reason: the backwards-compat shim `bot/services/greeting_service.py:202`
strips localized kwargs before delegating to `generate_greeting_card`, but
`generate_greeting_card` already accepts those kwargs natively. The shim is
dead code with zero test coverage; removing it is the DRY fix. Strict TDD
applies: a RED test exercising the native-kwargs path MUST be added before
deletion so the removal is guarded.)
(Migration: callers that still referenced the shim MUST call
`generate_greeting_card` directly with the localized kwargs; the shim's
fallback branch is unreachable so no behavior changes.)

## Scope boundary

Cycle 2 (Neon SVG via cairosvg/resvg) and Cycle 3 (timer, 12h, banana, RLS,
voice/moderation, ScheduledAction, has_perm) are OUT OF SCOPE for this change.
`bot/utils/time.py` (DB timestamp parsing) and `bot/utils/timeparse.py`
(duration parsing) are DIFFERENT domains and MUST NOT be merged.
