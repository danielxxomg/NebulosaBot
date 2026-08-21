# Delta for Welcome/Goodbye

Cycle 2 of 3. Adds the `gaming_neon` theme as a Pillow procedural branch in
`PillowGreetingRenderer` (hex polygon + `ImageFilter.GaussianBlur` glow, magenta→cyan
diagonal via `brand.ACCENT_A`→`brand.ACCENT_B`). The `GreetingRenderer` interface
is UNCHANGED — `render()` accepts an added optional `theme_id` parameter that
selects the theme, defaulting to the existing default theme. Neon stays Pillow
procedural for Cycle 2; the cairosvg/SVG path stays behind the existing probe
(`bot/bot.py:220-243`). Pillow is safe on `python:3.11-slim` without apt; all
Pillow work MUST run via `asyncio.to_thread`.

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

## MODIFIED Requirements

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

## Scope boundary

This delta adds the neon Pillow theme branch and the `theme_id` parameter. The
`theme_id` column, model round-trip, and avatar cache are specified in
`greeting-config`; the neon palette tokens are specified in `brand-tokens`.
The cairosvg/SVG path stays gated for Cycle 3+. Cycle 3
(voice/moderation, ScheduledAction, has_perm) is OUT OF SCOPE.
