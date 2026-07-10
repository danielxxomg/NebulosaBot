# Design: Type-Strict Cogs

## Technical Approach

Narrow the existing `bot.cogs.*` mypy exception to the only non-actionable error code, `untyped-decorator`. Repair the remaining 94 errors in place: parameterize every `commands.Context`, correct real nullable/member contracts, remove stale suppressions, and document the 25 discord.py hybrid decorator signature defects with code-specific inline ignores. This is a type-only refactor; command behavior, service calls, cache use, and Discord dispatch stay unchanged.

## Architecture Decisions

| Decision | Options / trade-off | Choice and rationale |
|---|---|---|
| Cogs override | Keep `arg-type` globally (small diff, hides real defects); remove all overrides (adds unfixable noise); retain one code. | Retain only `untyped-decorator`. `hybrid_command`/`hybrid_group` strips callable types in current discord.py stubs; all other codes can be made locally strict. |
| Hybrid decorator failures | Change command signatures to satisfy `Never` stubs; broad override; local suppressions. | Add `# type: ignore[arg-type]` with a `discord.py hybrid_command stub limitation` rationale on each affected decorator. Local ignores remain auditable and `unused-ignore` detects obsolete ones after stub upgrades. |
| Moderator narrowing | Widen `LoggingService` to accept `User`; cast; narrow at cog boundary. | Narrow `ctx.author` to `discord.Member` with existing assert/isinstance style before `log_moderation_action`. The service contract accurately requires a guild member and must not be weakened. |
| Nullable Discord data | Pass `None` to formatting/image APIs; cast; guard/coalesce. | Guard `target.joined_at` before `format_dt` and coalesce guild `member_count` to `0`. These represent real optional runtime values. |

## Data Flow

No runtime data flow changes. Static checking follows existing command boundaries:

    hybrid command -> Context[Any] -> guild/member narrowing -> LoggingService
                                           |
                                           +-> existing Discord/API behavior

Each decorator ignore applies only to the third-party stub's impossible callable signature. All real values pass through their existing services unchanged.

## File Changes

| File | Action | Description |
|---|---|---|
| `pyproject.toml` | Modify | Set the `bot.cogs.*` override to exactly `untyped-decorator`. |
| `bot/cogs/sentinel.py` | Modify | Parameterize contexts; narrow moderation actors before logging; annotate affected hybrid decorators. |
| `bot/cogs/tickets.py` | Modify | Parameterize contexts and annotate affected hybrid command/group decorators. |
| `bot/cogs/greetings.py` | Modify | Parameterize contexts, coalesce `member_count`, remove/update stale override ignores, and annotate affected decorators. |
| `bot/cogs/stellar.py` | Modify | Parameterize contexts, remove/update stale override ignore, and annotate affected decorators. |
| `bot/cogs/utility.py` | Modify | Parameterize contexts, guard nullable `joined_at`, and annotate affected decorators. |
| `bot/cogs/ocio.py` | Modify | Parameterize contexts and annotate affected decorators. |
| `bot/cogs/core.py` | Modify | Annotate affected hybrid decorators. |
| `bot/cogs/setup.py` | Modify | Parameterize context and annotate its hybrid decorator. |
| `tests/test_mypy_config.py` | Modify | Add a regression test requiring the cogs wildcard override and requiring its disabled-code list to be only `untyped-decorator`. |

## Interfaces / Contracts

```python
from typing import Any

def _guild_id(ctx: commands.Context[Any]) -> str: ...

# Before log_moderation_action(..., moderator=ctx.author, ...)
assert isinstance(ctx.author, discord.Member)

# Optional Discord field handling
member_count = ctx.guild.member_count or 0
if target.joined_at is not None:
    formatted_joined = discord.utils.format_dt(target.joined_at, "R")
```

`LoggingService.log_moderation_action(..., moderator: discord.Member, ...)` remains unchanged. Inline ignores must name `arg-type` only and include the stub-limitation rationale; no new per-module override is allowed.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | Mypy configuration guard | Extend `tests/test_mypy_config.py`; reject a missing cogs override or any disabled code beyond `untyped-decorator`. |
| Static | All cog annotations and suppressions | Run `uv run mypy bot/cogs/`; require zero errors. |
| Integration | Command behavior unchanged | Run `uv run pytest`; existing cog/service tests cover command paths without Discord API calls. |
| E2E | Not applicable | No external behavior changes. |

## Migration / Rollout

No migration required. Ship as one type-safety change. Roll back by restoring the previous cogs override and reverting source annotations; no persisted data or Discord state changes.

## Open Questions

None.
