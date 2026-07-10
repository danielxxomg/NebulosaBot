# QA Help Builder Specification

## Purpose

Unit tests for core help builder functions: `_build_cog_help_embed`, `_build_help_pages`, and `_resolve_prefix`.

## Requirements

### Requirement: _build_cog_help_embed renders commands

Tests MUST prove the help embed builder returns an embed for a cog with visible commands, and None for empty or missing cogs.

#### Scenario: returns embed for cog with visible commands

- GIVEN a mock bot with a cog containing 3 visible hybrid commands
- WHEN `_build_cog_help_embed(bot, "cog_name")` is called
- THEN a discord.Embed is returned listing the 3 commands

#### Scenario: returns None for empty cog

- GIVEN a mock bot with a cog that has no visible commands
- WHEN `_build_cog_help_embed(bot, "empty_cog")` is called
- THEN the return value is None

#### Scenario: returns None for missing cog

- GIVEN a mock bot with no cog matching the name
- WHEN `_build_cog_help_embed(bot, "nonexistent")` is called
- THEN the return value is None

### Requirement: _build_help_pages produces one page per cog

Tests MUST prove help page generation produces one embed per cog that has visible commands.

#### Scenario: multiple cogs produce multiple pages

- GIVEN a mock bot with 3 cogs (2 with commands, 1 empty)
- WHEN `_build_help_pages(bot)` is called
- THEN the result contains exactly 2 embeds

### Requirement: _resolve_prefix reads guild config

Tests MUST prove prefix resolution reads from guild config and falls back to default.

#### Scenario: prefix from guild config

- GIVEN a guild with a custom prefix "!"
- WHEN `_resolve_prefix(guild_id)` is called
- THEN the return value is "!"

#### Scenario: prefix fallback to default

- GIVEN a guild with no custom prefix configured
- WHEN `_resolve_prefix(guild_id)` is called
- THEN the return value is the default prefix
