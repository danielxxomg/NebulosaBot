# Delta for Brand Tokens

Cycle 2 of 3. Adds the `gaming_neon` theme palette — two neon tokens
(`accent_a #FF2E97` magenta, `accent_b #00E5FF` cyan) — to `bot/utils/brand.py`
for the neon greeting theme. The existing `ACCENT` token stays the default;
`GREETING_ACCENT` MUST NOT be reintroduced. The renderer source MUST remain
free of hex literals (the "zero hex outside `brand.py`" invariant from Cycle 1).

## ADDED Requirements

### Requirement: Neon theme accent tokens

The system MUST define two neon theme accent tokens in `bot/utils/brand.py`:
`ACCENT_A: int = 0xFF2E97` (magenta) and `ACCENT_B: int = 0x00E5FF` (cyan).
These tokens are the magenta→cyan diagonal source for the `gaming_neon`
greeting theme. The existing `ACCENT` token (`0xA855F7`) MUST remain the
default-theme accent and MUST NOT change value. `GREETING_ACCENT` MUST NOT
be reintroduced; the Cycle 1 alias is the only `GREETING_*` name allowed and
its value MUST stay `== ACCENT`.

#### Scenario: Neon tokens exported with exact values

- GIVEN `bot/utils/brand.py` after the change
- WHEN the module is imported
- THEN it exports `ACCENT_A == 0xFF2E97` and `ACCENT_B == 0x00E5FF` alongside the unchanged `ACCENT == 0xA855F7`

#### Scenario: No GREETING_ACCENT reintroduced

- GIVEN the renderer and brand modules after the change
- WHEN scanned for `GREETING_ACCENT` defined as a non-ACCENT value or a fresh neon constant
- THEN zero matches are found and neon colors are read from `brand.ACCENT_A`/`brand.ACCENT_B`

## MODIFIED Requirements

### Requirement: Brand color tokens

The system MUST define brand color constants in a `bot/utils/brand.py` module. The palette MUST use purple/violet family: PRIMARY (#9B5DE5), ACCENT (#A855F7), SUCCESS (#10B981), WARNING (#F59E0B), ERROR (#EF4444), INFO (#8B5CF6). The neon theme tokens `ACCENT_A` (#FF2E97) and `ACCENT_B` (#00E5FF) MAY be added as an opt-in theme palette used only by the `gaming_neon` greeting theme; they MUST NOT alter the default family or any default embed color.
(Previously: the palette listed the purple/violet family only and did not acknowledge an opt-in neon theme palette.)

#### Scenario: Brand module exists with all palette values

- GIVEN the bot codebase
- WHEN `bot/utils/brand.py` is imported
- THEN it exports PRIMARY, ACCENT, SUCCESS, WARNING, ERROR, INFO with the specified hex values and MAY export ACCENT_A/ACCENT_B for the neon theme

#### Scenario: Embeds use brand tokens not hardcoded colors

- GIVEN any embed color assignment in bot/ source code (excluding brand.py)
- WHEN the code is scanned for 6-digit hex literals (`#[0-9A-Fa-f]{6}`)
- THEN zero matches are found — all colors reference brand tokens

### Requirement: All cogs adopt brand palette

Every cog and service that builds embeds (Sentinel, Core, LoggingService, Stellar, Tickets, and the greeting renderer) MUST use brand tokens instead of hardcoded color constants. The greeting renderer MUST source its default accent from `brand.ACCENT` and its neon accent from `brand.ACCENT_A`/`brand.ACCENT_B`. The `#7289da` greeting accent (`GREETING_ACCENT`) and the two ticket-cog local `INFO` definitions (`#5865F2`) are explicitly in scope of this requirement. The neon hex literals `#FF2E97` and `#00E5FF` MUST NOT appear outside `brand.py` — the renderer imports the tokens.
(Previously: required the greeting renderer accent to be `brand.ACCENT` with no hex literal; did not cover the neon theme tokens or their import discipline.)

#### Scenario: No hardcoded colors in production embed code

- GIVEN all Python files under `bot/` (excluding `brand.py`)
- WHEN scanned for hardcoded 6-digit hex color literals in embed assignments
- THEN zero matches are found

#### Scenario: Greeting renderer has no hex literal

- GIVEN the split greeting renderer file under `bot/services/`
- WHEN scanned for 6-digit hex literals (`#[0-9A-Fa-f]{6}`)
- THEN zero matches are found — the default accent is `brand.ACCENT` and the neon accents are `brand.ACCENT_A`/`brand.ACCENT_B`

#### Scenario: Ticket cogs have no hex literals

- GIVEN `bot/cogs/ticket_admin_flow.py` and `bot/cogs/ticket_notes_flow.py`
- WHEN scanned for 6-digit hex literals
- THEN zero matches are found — both import `brand.INFO`

## Scope boundary

This delta adds only the two neon theme tokens and the import discipline that
keeps them out of the renderer source. The neon *rendering* (polygon, glow,
gradient) is specified in `welcome-goodbye`; the `theme_id` column and
dashboard selector are specified in `greeting-config`. Cycle 3
(voice/moderation, ScheduledAction, has_perm) is OUT OF SCOPE.
`bot/utils/time.py` and `bot/utils/timeparse.py` are DIFFERENT domains and
MUST NOT be merged.
