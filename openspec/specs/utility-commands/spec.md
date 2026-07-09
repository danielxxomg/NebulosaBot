# Utility Commands Specification

## Purpose

Provide guild members with quick, read-only information about users and the current server via hybrid commands.

## Requirements

### Requirement: Avatar command

The `/avatar` command MUST display the target user's avatar as a thumbnail embed.

#### Scenario: Self avatar

- GIVEN a member invokes `/avatar` without a target
- WHEN the command executes
- THEN the bot SHALL reply with an embed whose thumbnail is the invoking member's avatar URL

#### Scenario: Mentioned member avatar

- GIVEN a member invokes `/avatar @member`
- WHEN the command executes
- THEN the bot SHALL reply with an embed whose thumbnail is the mentioned member's avatar URL

### Requirement: Server info command

The `/serverinfo` command MUST return a guild summary embed containing name, owner, member count, channel count, role count, and creation date.

#### Scenario: Guild context

- GIVEN the command is invoked inside a guild
- WHEN the command executes
- THEN the bot SHALL reply with an embed showing the guild's name, owner mention, total members, channel count, role count, and creation timestamp

#### Scenario: DM context

- GIVEN the command is invoked in a DM channel
- WHEN the command executes
- THEN the bot SHALL reply with an error embed stating the command only works in servers

### Requirement: User info command

The `/userinfo` command MUST return a member summary embed with name, ID, roles, join date, and account creation date.

#### Scenario: Member with few roles

- GIVEN a member invokes `/userinfo` on a member with 20 or fewer roles
- WHEN the command executes
- THEN the bot SHALL reply with an embed listing all roles, plus join date and account creation date

#### Scenario: Member with many roles

- GIVEN a member invokes `/userinfo` on a member with more than 20 roles
- WHEN the command executes
- THEN the bot SHALL reply with an embed listing the first 20 roles followed by "and N more"

### Requirement: Shared EmbedPaginator utility

`_HelpPaginator` (core.py) and `_ModlogsPaginator` (sentinel.py) MUST be replaced with a unified custom `EmbedPaginator` in `bot/utils/paginator.py`. The `EmbedPaginator` MUST be a `discord.ui.View` subclass with previous/next/stop buttons and timeout handling. It MUST maintain existing UX: page navigation buttons and timeout behavior. (Note: `discord.ext.pages.Paginator` is from Pycord, not discord.py v2.7.1 — a custom paginator is required.)

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
