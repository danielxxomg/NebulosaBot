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

### Requirement: All cogs adopt brand palette

Every cog and service that builds embeds (Sentinel, Core, LoggingService, Stellar, Tickets) MUST use brand tokens instead of hardcoded color constants.

#### Scenario: No hardcoded colors in production embed code

- GIVEN all Python files under `bot/` (excluding `brand.py`)
- WHEN scanned for hardcoded 6-digit hex color literals in embed assignments
- THEN zero matches are found
