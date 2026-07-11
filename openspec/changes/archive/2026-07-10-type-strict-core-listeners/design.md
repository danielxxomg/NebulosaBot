# Design: Strict Core and Listener Typing

## Technical Approach

Apply the proposal's three mechanical tiers without changing Discord, database, cache, or listener behavior. Parameterize every in-scope raw database/SDK row mapping as `dict[str, Any]`; narrow only where Discord's stubs expose broader unions; and remove the three now-unnecessary mypy overrides. Update the configuration regression test to assert the new surviving-override contract.

## Architecture Decisions

| Option | Tradeoff | Decision and rationale |
|---|---|---|
| Type every raw row as `dict[str, Any]` | Preserves dynamic Supabase payload values | Chosen. The DB facade and Realtime SDK intentionally return unstructured rows; explicit key/value types remove `type-arg` errors without inventing schema models. |
| Introduce a `NebulosaBot` Protocol for `NebulosaContext` | More principled but adds circular-import/maintenance surface | Rejected. Keep the existing unparameterized context base with its justified `type: ignore[type-arg]`; cast the two service accessors after startup guarantees initialization. |
| Cast Discord channel values | Would suppress useful runtime validation | Rejected. Use `isinstance` narrowing so only a `GuildChannel` is passed to the logging visibility API and only a messageable configured target replaces `message.channel`. |
| Retain per-file mypy suppressions | Hides regressions in clean modules | Rejected. Remove `bot.core.*`, `bot.listeners.*`, and `bot.bot`; retain only the existing cogs and tests debt overrides. |

## Data Flow

No runtime data-flow change occurs. Type evidence follows existing values:

    Supabase / Realtime payload ──> dict[str, Any] annotations ──> existing DB/cache callers
    Discord Message.channel ──> isinstance narrowing ──> existing send/log paths
    setup_hook initializes db/cache ──> context cast ──> command service accessors

`NebulosaBot.get_context()` asserts its `super().get_context()` result is a `NebulosaContext` before assigning `_guild_config`; its public return type remains `commands.Context[NebulosaBot]` for the discord.py override contract.

## File Changes

| File | Action | Description |
|---|---|---|
| `bot/core/realtime.py`, `bot/core/i18n.py`, `bot/core/context.py` | Modify | Parameterize raw mappings; cast `self.bot.db` and `self.bot.cache` in context accessors. |
| `bot/core/db/{base,economy_db,greeting_db,guild_db,infraction_db,member_db,ticket_audit_db,ticket_category_db,ticket_db,ticket_note_db}.py` | Modify | Replace all in-scope bare `dict` / `list[dict]` annotations with `dict[str, Any]` equivalents. |
| `bot/bot.py` | Modify | Assert the created context is `NebulosaContext` before `_guild_config` assignment. |
| `bot/listeners/xp_listener.py` | Modify | Narrow the configured `guild.get_channel()` result before assigning it as the messageable send target. |
| `bot/listeners/audit_listener.py` | Modify | Return when `before.channel` is not `discord.abc.GuildChannel` before the visibility check. |
| `pyproject.toml` | Modify | Remove the three resolved mypy override blocks. |
| `tests/test_mypy_config.py` | Modify | Replace assertions requiring the `bot.bot` override with assertions that core, listeners, and bot overrides are absent; preserve cogs/tests expectations. |

## Interfaces / Contracts

No new public runtime interfaces. Raw data annotations consistently become:

```python
dict[str, Any]
list[dict[str, Any]]
```

The context remains deliberately unparameterized because importing the concrete bot type would form a runtime cycle. Its accessors make the lifecycle invariant explicit:

```python
return cast(Database, self.bot.db)
return cast(TTLCache, self.bot.cache)
```

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Static | All 42 reported errors and override removal | Temporarily-free strict check: `uv run mypy --strict --python-version 3.11 bot/core/ bot/listeners/ bot/bot.py`; then full project mypy. |
| Unit | Mypy configuration and existing listener routing/early exits | Update and run `tests/test_mypy_config.py`, `tests/test_xp_listener.py`, and `tests/test_audit_listener.py`. Add a guard regression only if existing mocks do not exercise the narrowed branch. |
| Regression | Bot behavior remains unchanged | Run `uv run pytest`; annotations, casts, and guards must preserve configured-channel fallback and valid guild edit logging. |

## Migration / Rollout

No migration required. This is annotation/configuration-only with defensive guards that match existing runtime assumptions. Roll back by restoring the three override blocks.

## Open Questions

None.
