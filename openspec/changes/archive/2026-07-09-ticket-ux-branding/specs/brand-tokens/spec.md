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
