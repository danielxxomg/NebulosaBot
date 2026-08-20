# Brand Tokens Specification

## Purpose

Purple/violet brand palette for all embed colors and bot avatar footer icon replacing hardcoded color constants.

## Requirements

### Requirement: Brand color tokens

The system MUST define brand color constants in a `bot/utils/brand.py` module. The palette MUST use purple/violet family: PRIMARY (#9B5DE5), ACCENT (#A855F7), SUCCESS (#10B981), WARNING (#F59E0B), ERROR (#EF4444), INFO (#8B5CF6).

#### Scenario: Brand module exists with all palette values

- GIVEN the bot codebase
- WHEN `bot/utils/brand.py` is imported
- THEN it exports PRIMARY, ACCENT, SUCCESS, WARNING, ERROR, INFO with the specified hex values

#### Scenario: Embeds use brand tokens not hardcoded colors

- GIVEN any embed color assignment in bot/ source code (excluding brand.py)
- WHEN the code is scanned for 6-digit hex literals (`#[0-9A-Fa-f]{6}`)
- THEN zero matches are found — all colors reference brand tokens

### Requirement: Bot avatar footer icon

The default embed footer icon MUST use `bot.user.display_avatar.url` instead of hardcoded URLs.

#### Scenario: Default embed uses bot avatar

- GIVEN an embed built with `_make_embed()`
- WHEN no guild context is provided
- THEN the footer icon uses `bot.user.display_avatar.url`

### Requirement: Guild-context footer and thumbnail

Embeds in guild-specific contexts (tickets, logging, moderation) MUST use `guild.icon.url` as footer or thumbnail when available, falling back to bot avatar.

#### Scenario: Guild embed uses guild icon

- GIVEN a guild with a custom icon set
- WHEN a guild-context embed is rendered (ticket, log, moderation)
- THEN the footer or thumbnail uses `guild.icon.url`

#### Scenario: Guild without icon falls back to bot avatar

- GIVEN a guild without a custom icon
- WHEN a guild-context embed is rendered
- THEN the footer icon falls back to `bot.user.display_avatar.url`

### Requirement: Greeting card accent uses brand tokens

The greeting card renderer MUST source its accent color from
`bot/utils/brand.py` (the existing `ACCENT` token) and MUST NOT define a
`GREETING_ACCENT` constant or hardcode `#7289da`. This is the greeting-side
half of the existing "All cogs adopt brand palette" requirement, scoped here
because the greeting renderer is being split in this change.

#### Scenario: No GREETING_ACCENT constant remains

- GIVEN the split greeting renderer source
- WHEN scanned for `GREETING_ACCENT` or the literal `7289da`
- THEN zero matches are found and the accent is read from `brand.ACCENT`

### Requirement: Ticket cog INFO uses brand.INFO

The two local `INFO = discord.Color.from_str("#5865F2")` definitions in
`bot/cogs/ticket_admin_flow.py:27` and `bot/cogs/ticket_notes_flow.py:21`
MUST be removed and replaced by an import of `bot.utils.brand.INFO`. No
`from_str("#...")` hex construction MAY remain in those files. The `INFO` token
in `brand.py` is the single source of truth.

#### Scenario: ticket_admin_flow imports brand.INFO

- GIVEN `bot/cogs/ticket_admin_flow.py`
- WHEN scanned for `discord.Color.from_str` or the literal `5865F2`
- THEN zero matches are found and the file imports `INFO` from `bot.utils.brand`

#### Scenario: ticket_notes_flow imports brand.INFO

- GIVEN `bot/cogs/ticket_notes_flow.py`
- WHEN scanned for `discord.Color.from_str` or the literal `5865F2`
- THEN zero matches are found and the file imports `INFO` from `bot.utils.brand`

### Requirement: All cogs adopt brand palette

Every cog and service that builds embeds (Sentinel, Core, LoggingService,
Stellar, Tickets, and the greeting renderer) MUST use brand tokens instead of
hardcoded color constants. The greeting card accent (`#7289da` via
`GREETING_ACCENT`) and the two ticket-cog local `INFO` definitions
(`#5865F2`) are explicitly in scope of this requirement.

#### Scenario: No hardcoded colors in production embed code

- GIVEN all Python files under `bot/` (excluding `brand.py`)
- WHEN scanned for hardcoded 6-digit hex color literals in embed assignments
- THEN zero matches are found

#### Scenario: Greeting renderer has no hex literal

- GIVEN the split greeting renderer file under `bot/services/`
- WHEN scanned for 6-digit hex literals (`#[0-9A-Fa-f]{6}`)
- THEN zero matches are found — the accent is `brand.ACCENT`

#### Scenario: Ticket cogs have no hex literals

- GIVEN `bot/cogs/ticket_admin_flow.py` and `bot/cogs/ticket_notes_flow.py`
- WHEN scanned for 6-digit hex literals
- THEN zero matches are found — both import `brand.INFO`
