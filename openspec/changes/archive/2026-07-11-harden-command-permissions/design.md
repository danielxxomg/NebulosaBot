# Design: Harden Command Permissions

## Technical Approach

Make `is_mod()` match the proven dual-registration structure of `is_admin()`: apply an `app_commands.check` for slash invocations and a `commands.check` for prefix invocations. The existing `is_mod_check(interaction)` remains the stable, non-raising boolean API for ticket-view callbacks. Slash behavior remains unchanged; the new prefix predicate applies the same admin-or-configured-role policy and raises prefix-command exceptions.

## Architecture Decisions

| Decision | Options / trade-off | Choice and rationale |
|---|---|---|
| Hybrid guard shape | Separate decorators; permission registry/factory | Mirror `is_admin()` with nested `commands.check(prefix)(app_commands.check(slash)(func))`. It is the project’s working pattern and fixes every existing `@is_mod()` hybrid command without cog edits. |
| Shared role lookup | Duplicate cache lookup; make a DB read; shared private resolver | Extract the cache parsing into a private resolver that accepts `bot` and `guild_id`, then retain the interaction resolver and add a context resolver. Both paths use `_guild_mod_role_cache`; no event-loop DB I/O or cache-policy change. |
| Decision reuse | Change `is_mod_check()` to raise; duplicate all logic | Preserve `is_mod_check()` unchanged for button callbacks. The slash predicate continues to await it. The prefix predicate mirrors its ordered decision against `ctx.author`, `ctx.bot`, and `ctx.guild`, because it cannot supply an `Interaction`. |
| Prefix errors | `app_commands` errors; generic `False`; prefix `commands` errors | Raise `commands.NoPrivateMessage` for DMs, `commands.CheckFailure` for non-members/unconfigured roles, and `commands.MissingRole` for configured-but-missing roles. These are handled by the prefix command error path. |

## Data Flow

```text
Prefix !warn                  Slash /warn                 Button callback
    |                              |                            |
commands.check                 app_commands.check         is_mod_check()
    |                              |                            |
prefix predicate              is_mod_check(interaction)    bool only
    |                              |                            |
ctx.bot + guild.id -------- _guild_mod_role_cache -------- interaction.client + guild_id
    |                              |                            |
commands exception / True     app_commands exception/True  False / True
```

The shared resolver converts the cached string role ID to `int`, logs malformed values, and returns `None`. A cache miss or invalid value preserves deny-by-default: administrators pass; other users are denied.

## File Changes

| File | Action | Description |
|---|---|---|
| `bot/utils/checks.py` | Modify | Add context-capable cache resolution and `is_mod()` prefix predicate; compose both check decorators and expose `predicate` plus `prefix_predicate`, as `is_admin()` does. |
| `tests/test_checks.py` | Modify | Add RED-first unit coverage for predicate exposure, prefix success cases, and each required prefix exception while retaining slash and button contracts. |
| `tests/test_sentinel_cog.py` | Modify | Assert the real `warn` hybrid command has a command-level prefix check as an integration wiring regression test. |

## Interfaces / Contracts

```python
async def is_mod_check(interaction: discord.Interaction) -> bool:
    """Stable button-callback contract: never raises; returns authorization."""

# Decorator test hooks, matching is_admin().
is_mod().predicate: Callable[[discord.Interaction], Awaitable[bool]]
is_mod().prefix_predicate: Callable[[commands.Context[Any]], Awaitable[bool]]
```

`_resolve_mod_role_id_from_context(ctx)` (or an equivalent context wrapper over the shared cache resolver) is private. It must read `ctx.bot` and the current guild ID only; it must not alter the public button API.

## Testing Strategy

Strict RED → GREEN → REFACTOR order: add one focused failing test, run it and confirm failure because the prefix gate is absent, implement the minimum change, then rerun it. Do not write production changes before the RED suite is observed.

| Layer | What to Test | Approach |
|---|---|---|
| Unit | Decorator exposes both predicates; DM, non-member, unconfigured role, and missing configured role deny with `commands` exceptions | Invoke `is_mod().prefix_predicate` using mocked `Context`, `Member`, and cache. |
| Unit | Admin and configured-role member pass prefix; current slash and `is_mod_check` behavior remains intact | Reuse existing cache/member fixtures and assertions. |
| Integration | `SentinelCog.warn.checks` is non-empty | Instantiate the real cog and inspect the hybrid command’s prefix check list. |
| Regression | Full Python suite and coverage gate | Run `uv run pytest`; project config requires `--cov-fail-under=75`. |

## Migration / Rollout

No migration required. This takes effect at bot restart/redeploy and changes no persisted data. Roll back by reverting `bot/utils/checks.py`; prefix commands revert to the prior insecure behavior, so rollback requires an explicit security decision.

## Open Questions

None. The proposal’s intentional deny-by-default policy and exclusion of Discord guild-permission enforcement are retained.
