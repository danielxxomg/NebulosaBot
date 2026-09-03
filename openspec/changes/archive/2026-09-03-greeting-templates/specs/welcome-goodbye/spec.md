# Delta for welcome-goodbye

## ADDED Requirements

### Requirement: Template registry — four code-owned brand-only templates

The system MUST provide code-owned `TEMPLATE_REGISTRY` in `bot/services/greeting_renderer.py` with exactly four entries `default`, `gaming_neon`, `sunset_wave`, `minimal_light` mapping to procedural Pillow via `brand.py` tokens only (no DB/assets/fonts). Unknown/null MUST render `default`. `gaming_neon` byte-identity MUST be preserved (`_render_neon_overlay` + `GaussianBlur`). Renderer MUST NOT call `t()` and MUST affect only card image.

#### Scenario: Registry contains four templates

- GIVEN `TEMPLATE_REGISTRY` after change
- WHEN enumerated
- THEN keys are exactly the four names

#### Scenario: Unknown falls back to default

- GIVEN config `welcome_template_id="unknown_xyz"`
- WHEN `select_template(...,"welcome")` renders
- THEN `default` renders

#### Scenario: gaming_neon byte-identity preserved

- GIVEN `gaming_neon` before and after the change
- WHEN PNG bytes compared (same inputs)
- THEN bytes identical and glow uses `GaussianBlur` + `ACCENT_A/B`

#### Scenario: Renderer stays t()-free and card-image-only

- GIVEN `GreetingRenderer.render` after the change
- WHEN source scanned for `t(` and CTA audited
- THEN zero `t()` calls and text/CTA remain in services/cogs

### Requirement: Per-kind template selection policy

The system MUST expose `select_template(config, kind: "welcome"|"goodbye") -> str` with chain `welcome_template_id`/`goodbye_template_id` → `theme_id` → `default`. `GreetingService.dispatch_greeting` MUST call it per kind and pass resolved `template_id` (alias `theme_id`) to `GreetingRenderer.render`. Kinds MAY differ.

#### Scenario: Welcome resolves welcome_template_id

- GIVEN `welcome_template_id="sunset_wave"`, `goodbye_template_id="default"`, `theme_id="gaming_neon"`
- WHEN `select_template(config, "welcome")` called
- THEN returns `sunset_wave`

#### Scenario: Goodbye resolves goodbye_template_id

- GIVEN same config
- WHEN `select_template(config, "goodbye")` called
- THEN returns `default`

#### Scenario: Fallback to legacy themeId

- GIVEN `welcome_template_id=None`, `theme_id="gaming_neon"`
- WHEN `select_template(config, "welcome")` called
- THEN returns `gaming_neon`

#### Scenario: Fallback to default when both absent

- GIVEN `welcome_template_id=None`, `theme_id=None`
- WHEN `select_template(config, "welcome")` called
- THEN returns `default`

## MODIFIED Requirements

### Requirement: GreetingRenderer interface

The system MUST define `GreetingRenderer` protocol accepting identity inputs plus pre-translated `greeting_title`/`member_count_text` returning PNG, and MUST accept optional `template_id: str | None` (alias `theme_id`) on `render()` defaulting to `default` when null/unrecognised. Interface MUST NOT resolve translations. `GreetingService` MUST depend on interface (single injection) and MUST pass resolved id from `select_template`; null/unrecognised MUST render `default`. Backwards-compatible.
(Previously: interface accepted `theme_id` for single shared theme; now per-kind `template_id` with legacy alias.)

#### Scenario: Service depends on interface

- GIVEN `GreetingRenderer` is a protocol
- WHEN `GreetingService` constructed at `bot/bot.py:215`
- THEN it holds `GreetingRenderer` instance

#### Scenario: Interface receives translated strings only

- GIVEN `GreetingRenderer` implementation
- WHEN `render(...)` invoked
- THEN signature accepts `greeting_title`/`member_count_text` and MUST NOT call `t()`

#### Scenario: Interface accepts template_id and stays translation-free

- GIVEN protocol after the change
- WHEN `render(..., template_id="sunset_wave")` or `theme_id="gaming_neon"` invoked
- THEN accepts either name and MUST NOT call `t()`

#### Scenario: Default renders when template_id null

- GIVEN resolved template null
- WHEN `dispatch_greeting` calls renderer
- THEN `template_id=None` and `default` renders

#### Scenario: Unknown template_id falls back to default

- GIVEN resolved template unrecognised
- WHEN renderer invoked
- THEN `default` renders with no raise

### Requirement: Pillow is the default renderer

The system MUST ship `PillowGreetingRenderer` as default for four templates `default`, `gaming_neon`, `sunset_wave`, `minimal_light`. Rendering MUST use `brand.py` tokens only (`ACCENT`, `ACCENT_A`/`B`, `WARNING`/`ERROR`/`CARD_BG_*`/`MUTED_TEXT`/`PANEL_OVERLAY`) and MUST NOT hardcode hex. MUST run via `asyncio.to_thread`.
(Previously: default for `default`+`gaming_neon` only; now four brand-only templates.)

#### Scenario: Default render uses brand tokens

- GIVEN `PillowGreetingRenderer` injected, template null/`default`
- WHEN card rendered
- THEN accent from `brand.ACCENT`, no hex in source

#### Scenario: Neon render uses neon tokens

- GIVEN template `gaming_neon`
- WHEN card rendered
- THEN accents from `brand.ACCENT_A`/`B`, no hex

#### Scenario: Sunset and minimal use existing tokens

- GIVEN template `sunset_wave` or `minimal_light`
- WHEN card rendered
- THEN colors from existing `brand.py` tokens only

#### Scenario: Render runs off event loop

- GIVEN greeting dispatch in flight
- WHEN `dispatch_greeting` calls renderer
- THEN wrapped in `asyncio.to_thread`

## Scope boundary

Dashboard, DB catalogue, ephemeral preview, `rank_renderer.py`, text/CTA out of scope. `greetings.py` untouched.
