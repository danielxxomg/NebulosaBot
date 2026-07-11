# Delta for utility-commands

## MODIFIED Requirements

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
