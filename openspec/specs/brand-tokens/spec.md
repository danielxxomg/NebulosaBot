# Brand Tokens Specification

## Purpose

Purple/violet brand palette for all embed colors and bot avatar footer icon replacing hardcoded color constants.

## Requirements

### Requirement: Brand color tokens

The system MUST define brand color constants in a `bot/utils/brand.py` module. The palette MUST use purple/violet family: PRIMARY (#9B5DE5), ACCENT (#A855F7), SUCCESS (#10B981), WARNING (#F59E0B), ERROR (#EF4444), INFO (#8B5CF6).

#### Scenario: Brand module exists

- GIVEN the bot codebase
- WHEN `bot/utils/brand.py` is imported
- THEN it exports PRIMARY, ACCENT, SUCCESS, WARNING, ERROR, INFO color constants

#### Scenario: Embeds use brand colors

- GIVEN any embed built via `_make_embed()` or `build_ticket_embed()`
- WHEN the embed is rendered
- THEN the embed color uses a brand token (not the old `COLOR_*` constants)

### Requirement: Bot avatar footer icon

The default embed footer icon MUST use `bot.user.display_avatar.url` instead of the hardcoded imgur URL.

#### Scenario: Footer uses bot avatar

- GIVEN an embed built with `_make_embed()`
- WHEN the footer icon is set
- THEN the icon URL resolves to `bot.user.display_avatar.url`

### Requirement: Guild icon for guild-context embeds

Embeds in guild-specific contexts (ticket panel, logging, server info) MUST use `guild.icon.url` as the footer or thumbnail icon when available.

#### Scenario: Ticket panel uses guild icon

- GIVEN a guild with a custom icon
- WHEN the ticket panel embed is rendered
- THEN the embed footer or thumbnail uses `guild.icon.url`

#### Scenario: Guild has no icon fallback

- GIVEN a guild without a custom icon
- WHEN a guild-context embed is rendered
- THEN the embed falls back to `bot.user.display_avatar.url`

### Requirement: All cogs adopt brand palette

Every cog and service that builds embeds (sentinel, stellar, core, logging_service, etc.) MUST use brand tokens instead of the old `COLOR_*` constants.

#### Scenario: Logging service uses brand colors

- GIVEN `LoggingService` builds a log embed
- WHEN the embed color is set
- THEN it uses a brand token from `bot/utils/brand.py`

#### Scenario: Sentinel uses brand colors

- GIVEN `SentinelCog` builds a moderation embed
- WHEN the embed color is set
- THEN it uses a brand token instead of `COLOR_ERROR`/`COLOR_SUCCESS`/etc.

### Requirement: Brand token contract tests

The system MUST have contract tests proving all 6 brand tokens (PRIMARY, ACCENT, SUCCESS, WARNING, ERROR, INFO) are importable from `bot/utils/brand.py` with correct hex values. Tests MUST also prove no production module uses hardcoded hex color literals instead of brand tokens.

#### Scenario: all 6 tokens are importable

- GIVEN the `bot.utils.brand` module
- WHEN each of PRIMARY, ACCENT, SUCCESS, WARNING, ERROR, INFO is imported
- THEN no ImportError is raised

#### Scenario: token hex values match palette spec

- GIVEN the brand module constants
- WHEN their hex values are inspected
- THEN PRIMARY is `#9B5DE5`, ACCENT is `#A855F7`, SUCCESS is `#10B981`, WARNING is `#F59E0B`, ERROR is `#EF4444`, INFO is `#8B5CF6`

#### Scenario: no hardcoded hex in production code

- GIVEN all files under `bot/` (excluding `brand.py`)
- WHEN a regex scan for 6-digit hex literals (`#[0-9A-Fa-f]{6}`) is performed
- THEN zero matches are found in embed color assignments
