# QA Help Builder Specification

## Purpose

Unit tests for core help builder functions: `_build_cog_help_embed`, `_build_help_pages`, and `_resolve_prefix`.

## Requirements

### Requirement: _build_cog_help_embed renders commands

Tests MUST prove the help embed builder returns an embed for a cog with visible slash commands, and None for empty or missing cogs. Help MUST display slash syntax only (`/command`), not prefix examples, per `bot-core` (prefix inert `get_prefix=[]`).

(Previously: described visible hybrid commands)

#### Scenario: returns embed for cog with visible commands

- GIVEN a mock bot with a cog containing 3 visible slash commands (`@app_commands.command()`)
- WHEN `_build_cog_help_embed(bot, "cog_name")` is called
- THEN a `discord.Embed` is returned listing the 3 commands with `/` syntax

#### Scenario: returns None for empty cog

- GIVEN a mock bot with a cog that has no visible slash commands
- WHEN `_build_cog_help_embed(bot, "empty_cog")` is called
- THEN the return value is None

#### Scenario: returns None for missing cog

- GIVEN a mock bot with no cog matching the name
- WHEN `_build_cog_help_embed(bot, "nonexistent")` is called
- THEN the return value is None

#### Scenario: Help shows slash syntax only

- GIVEN a cog with visible slash commands
- WHEN the embed is built
- THEN every entry shows `/command` and none shows prefix example

### Requirement: _build_help_pages produces one page per cog

Tests MUST prove help page generation produces one embed per cog that has visible slash commands, with slash syntax only.

#### Scenario: multiple cogs produce multiple pages

- GIVEN a mock bot with 3 cogs (2 with slash commands, 1 empty)
- WHEN `_build_help_pages(bot)` is called
- THEN the result contains exactly 2 embeds with slash syntax

### Requirement: _resolve_prefix reads guild config

Tests MUST prove prefix resolution reads from guild config as data-only (persists `prefix` field) but does NOT gate command invocation. `get_prefix` MUST resolve to `[]` regardless of stored prefix; stored `prefix` is data-only for display/backward compatibility, verified via `t()` where user-facing.

(Previously: prefix read implied active command dispatch)

#### Scenario: prefix from guild config data-only

- GIVEN a guild with stored prefix "!" (legacy data)
- WHEN `_resolve_prefix(guild_id)` is called or config is read
- THEN the stored value is returned for data purposes but `get_prefix` remains `[]` and no prefix command is invocable

#### Scenario: prefix fallback to default data-only

- GIVEN a guild with no custom prefix configured
- WHEN the config is read
- THEN the default `prefix` value is returned as data but command dispatch remains slash-only

#### Scenario: Prefix dispatch inert

- GIVEN any guild with any stored prefix
- WHEN a user sends `!help` or `nb!help` as text
- THEN no command is invoked (help is slash `/help`)
