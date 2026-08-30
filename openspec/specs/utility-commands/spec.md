# Utility Commands Specification

## Purpose

Provide guild members with quick, read-only information about users and the current server via slash-only commands. Bot core is slash-only (`get_prefix -> []`).

## Requirements

### Requirement: Avatar command

The system MUST provide a slash-only `/avatar [member]` command via `@app_commands.command()` (MUST NOT use `hybrid_command`; prefix inert via `get_prefix -> []`) that displays the target user's avatar as a full-size embed image using `set_image` with `?size=1024`. Errors MUST use `t()`.

(Previously: purpose described hybrid commands; command was implicitly hybrid)

#### Scenario: Self avatar

- GIVEN a member invokes `/avatar` without target via slash
- WHEN the command executes
- THEN the embed image is the invoker's avatar URL with `?size=1024` via `set_image`

#### Scenario: Mentioned member avatar

- GIVEN a member invokes `/avatar @member` via slash
- WHEN the command executes
- THEN the embed image is the mentioned member's avatar URL

#### Scenario: Prefix inert

- GIVEN a user sends `nb!avatar` as text
- WHEN the message is processed
- THEN no command is invoked

### Requirement: Server info command

The system MUST provide a slash-only `/serverinfo` command via `@app_commands.command()` that returns a guild summary embed (name, owner, member count, channel count, role count, creation date). DM errors MUST use `t()`.

(Previously: implicitly hybrid via purpose)

#### Scenario: Guild context

- GIVEN the command is invoked inside a guild via slash
- WHEN the command executes
- THEN an embed shows name, owner mention, members, channels, roles, creation timestamp

#### Scenario: DM context

- GIVEN the command is invoked in a DM via slash
- WHEN the command executes
- THEN an error embed via `t()` states it only works in servers

### Requirement: User info command

The system MUST provide a slash-only `/userinfo [member]` command via `@app_commands.command()` that returns a member summary embed with name, ID, roles, join date, and account creation date. Prefix inert.

(Previously: implicitly hybrid)

#### Scenario: Member with few roles

- GIVEN a member invokes `/userinfo` via slash on a member with ≤20 roles
- WHEN the command executes
- THEN an embed lists all roles plus join and creation dates

#### Scenario: Member with many roles

- GIVEN a member invokes `/userinfo` via slash on a member with >20 roles
- WHEN the command executes
- THEN an embed lists the first 20 roles followed by "and N more"
### Requirement: Shared EmbedPaginator utility

`_HelpPaginator` (core.py) and `_ModlogsPaginator` (sentinel.py) MUST be replaced with a unified custom `EmbedPaginator` in `bot/utils/paginator.py`. The `EmbedPaginator` MUST be a `discord.ui.View` subclass with previous/next/stop buttons and timeout handling. It MUST maintain existing UX: page navigation buttons and timeout behavior. The constructor MUST accept a `guild_id` parameter. Button labels MUST be resolved via `t(guild_id, key)` using the guild's language. (Note: `discord.ext.pages.Paginator` is from Pycord, not discord.py v2.7.1 — a custom paginator is required.)

(Previously: button labels were hardcoded English; no guild_id parameter)

#### Scenario: Help pages render

- GIVEN a user invokes `/help` with multiple pages
- WHEN the paginator is displayed
- THEN prev/next navigation works and pages render correctly

#### Scenario: Modlogs pages render

- GIVEN a user invokes `/modlogs` with multiple pages
- WHEN the paginator is displayed
- THEN prev/next navigation works and pages render correctly

#### Scenario: Timeout behavior preserved

- GIVEN a paginator is displayed
- WHEN 120 seconds pass with no interaction
- THEN the paginator times out and buttons become disabled

#### Scenario: Spanish guild shows localized buttons

- GIVEN a guild with language `es`
- WHEN an `EmbedPaginator` is created with `guild_id`
- THEN Previous/Next/Stop button labels are resolved via `t()` in Spanish

#### Scenario: English guild shows localized buttons

- GIVEN a guild with language `en`
- WHEN an `EmbedPaginator` is created with `guild_id`
- THEN Previous/Next/Stop button labels are resolved via `t()` in English

### Requirement: count_open_tickets_by_category uses count="exact"

`count_open_tickets_by_category` MUST use `count="exact"` on the Supabase query instead of fetching all rows and calling `len()`.

#### Scenario: Count without fetching rows

- GIVEN 50 open tickets across 3 categories
- WHEN `count_open_tickets_by_category(guild_id)` is called
- THEN the count is returned without fetching all 50 rows into memory

### Requirement: TTLCache.size public property

`TTLCache` MUST expose a public `size` property that returns the number of entries. Code MUST NOT access `_store` directly outside the class.

#### Scenario: size returns entry count

- GIVEN a cache with 5 entries
- WHEN `cache.size` is called
- THEN 5 is returned

#### Scenario: No direct _store access

- GIVEN the `size` property exists
- WHEN inspecting code outside `cache.py`
- THEN no code accesses `cache._store` directly

### Requirement: Remove redundant permission decorators

Redundant `@commands.has_permissions(administrator=True)` decorators in `greetings.py` and `setup.py` MUST be collapsed. `setup.py` already has `@is_admin()` — the `@has_permissions` is redundant. `greetings.py` does manual `guild_permissions.administrator` checks — the `@has_permissions` decorator duplicates them.

#### Scenario: setup.py decorator cleanup

- GIVEN `/setup` has both `@commands.has_permissions(administrator=True)` and `@is_admin()`
- WHEN cleanup runs
- THEN only `@is_admin()` remains

#### Scenario: greetings.py decorator cleanup

- GIVEN `/welcome_test` and `/goodbye_test` have `@commands.has_permissions(administrator=True)` plus manual admin checks
- WHEN cleanup runs
- THEN the redundant `@has_permissions` decorator is removed; manual checks or `@is_admin()` handle authorization
