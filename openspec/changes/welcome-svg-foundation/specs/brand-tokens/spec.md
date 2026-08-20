# Delta for Brand Tokens

Cycle 1. Restores the "zero hex outside `brand.py`" invariant the existing
spec already requires but which is violated in three places: the greeting card
accent `#7289da` (bypass via `GREETING_ACCENT`), and two local `INFO =
discord.Color.from_str("#5865F2")` definitions in ticket cogs. This delta adds
scenarios that close those gaps.

## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: All cogs adopt brand palette

Every cog and service that builds embeds (Sentinel, Core, LoggingService,
Stellar, Tickets, and the greeting renderer) MUST use brand tokens instead of
hardcoded color constants. The greeting card accent (`#7289da` via
`GREETING_ACCENT`) and the two ticket-cog local `INFO` definitions
(`#5865F2`) are explicitly in scope of this requirement.

(Previously: the requirement named cogs and services but did not call out the
greeting card `#7289da` bypass or the two ticket-cog `INFO` bypasses, both of
which violate "zero hex outside brand.py".)

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

## Scope boundary

This delta is the "zero-hex restored" half of Cycle 1. It does not change the
brand palette values, the footer-icon behavior, or the guild-context
footer/thumbnail behavior already specified. Cycle 2/3 scope (Neon, timer,
12h, banana, RLS, voice/moderation, ScheduledAction, has_perm) is OUT OF SCOPE.
