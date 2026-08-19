# Delta for Ticket Commands

## ADDED Requirements

### Requirement: Flow-aligned cog split with stable registration

The ticket cog MUST be physically split into administration, lifecycle, notes, and integrity flow modules behind a stable `TicketsCog` facade. Hybrid command names, command permissions, interaction responses, listeners, background tasks, and `async def setup(bot)` registration MUST remain compatible.

#### Scenario: Command registration survives extraction

- GIVEN the bot loads the ticket extension after the split
- WHEN `setup(bot)` executes
- THEN the same hybrid commands and listeners are registered exactly once

#### Scenario: Existing command behavior survives extraction

- GIVEN an administrator or moderator invokes an existing ticket command
- WHEN the command is handled by its extracted flow module
- THEN its permission result, guild-scoped response, and service call remain unchanged

### Requirement: Guild-scoped command database boundary

Every direct database lookup retained or moved from `TicketsCog` MUST carry the invoking guild ID or delegate to a service method that enforces ownership before disclosure or mutation. The former sub-ticket, transfer, and category-edit callers at `tickets.py:568`, `tickets.py:685`, and `tickets.py:722` MUST have no guild-scope gap; all 14 direct `self.bot.db` references MUST receive the same audit.

#### Scenario: Deferred caller gaps are closed

- GIVEN a command resolves a ticket by channel before sub-ticket creation, transfer, or category edit
- WHEN the lookup runs in guild A
- THEN only the guild A ticket is eligible and another guild's row is neither returned nor changed

#### Scenario: Cross-guild command input is denied

- GIVEN a command receives a ticket or channel identifier owned by guild B
- WHEN a guild A actor invokes the command
- THEN the command returns a safe denial/error and performs no guild B mutation

### Requirement: S3 guardrail gate

The command split MUST NOT be accepted as complete until the complete S3 gate is green: `uv run pytest` reports the 1,864-pass/5-skip baseline or an approved equivalent, `uv run mypy bot` and `uv run mypy tests` report zero errors, `uv run ruff check bot tests scripts` reports zero findings including all 11 baseline `scripts/` findings, the `GUILD_SCOPE_GAPS` ledger is empty, and permission, live-schema, DDL, service, cog, and view contracts pass.

#### Scenario: Guardrail failure blocks completion

- GIVEN any guild gap, Ruff finding, type error, failed contract, or incomplete live/DDL gate remains
- WHEN S3 completion is evaluated
- THEN the change remains incomplete and no downstream slice is considered green
