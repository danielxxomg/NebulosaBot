# Design: Type-Strict Services

## Technical Approach

Remove the `bot.services.*` mypy exemption and resolve every resulting service error locally, preserving runtime behavior and the existing cache-first/service boundaries. This implements the proposal's source-fix approach: type the service boundary around untyped core APIs, and use narrow inline ignores only where third-party stubs cannot describe a runtime-valid operation.

## Architecture Decisions

| Decision | Options / trade-off | Choice and rationale |
|---|---|---|
| Cache typing | Generic `TTLCache[T]` fixes the root globally but expands core scope; local cast retains the cache's heterogeneous design. | Cast validated cache-hit values in the three services. Generic cache refactoring is explicitly deferred. |
| DB-row typing | Type all `bot.core.db` returns now, or document typed service contracts. | Use `dict[str, Any]` in affected service signatures only. Core remains separately exempt and outside this refactor. |
| Stub failures | Suppress per module, or retain a wildcard override. | Inline, code-specific suppressions with a runtime rationale. This is auditable and does not hide future service errors. |

## Data Flow

No runtime flow changes. Type information constrains existing boundaries only:

    TTLCache.get() -> Any | None -> service cast -> typed model/list
    Database row -> dict (core boundary) -> dict[str, Any] service contract
    discord.py/Pillow runtime API -> incomplete stub -> documented inline ignore

Cache keys, DB queries, Supabase access, and Discord dispatch remain unchanged.

## File Changes

| File | Action | Per-file fix approach |
|---|---|---|
| `pyproject.toml` | Modify | Delete the `bot.services.*` override; retain unrelated debt overrides. |
| `bot/services/guild_service.py` | Modify | Import `cast`; cast non-`None` config cache hit to `GuildConfig`. |
| `bot/services/greeting_service.py` | Modify | Cast cached config; annotate helpers with `discord.Member` and `discord.abc.Messageable`; coalesce `member.guild.member_count` to `0` before image generation. |
| `bot/services/economy_service.py` | Modify | Import `Any`/`cast`; type leaderboard/config contracts as `dict[str, Any]`; cast cached leaderboard to `list[dict[str, Any]]`. |
| `bot/services/ticket_service.py` | Modify | Replace reopening helper's bare DB-row `dict` annotations with `dict[str, Any]`. |
| `bot/services/ticket_invariants.py` | Modify | Replace ticket-row `dict` annotations with `dict[str, Any]`. |
| `bot/services/logging_service.py` | Modify | Add `# type: ignore[arg-type]` only at the two `can_log_in_channel(message.channel)` calls; Discord's message-channel union is broader than the runtime text-channel guard accepts. |
| `bot/services/image_service.py` | Modify | Add `# type: ignore[attr-defined]` at both `Image.LANCZOS` uses; Pillow exposes the constant at runtime but its stubs omit it. |
| `tests/test_mypy_config.py` | Modify | Add a configuration regression assertion that no override targets `bot.services.*`. |

## Interfaces / Contracts

```python
async def get_leaderboard(...) -> list[dict[str, Any]]: ...
async def get_economy_config(...) -> dict[str, Any] | None: ...
def check_can_unclaim(actor_id: str, ticket: dict[str, Any], *, is_mod: bool) -> None: ...
```

`cast()` narrows only after the established cache key and owning service select the expected value. It does not alter cache storage or public runtime contracts.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | Mypy configuration regression | Extend `tests/test_mypy_config.py` to reject `bot.services.*` override. |
| Static | All service annotations and suppressions | Run `uv run mypy bot/services/`; require zero errors. |
| Integration | Behavior preservation | Run `uv run pytest`; existing service tests cover cache hits, greeting dispatch, logging routing, and image output. |
| E2E | Not applicable | No external behavior or Discord API change. |

## Migration / Rollout

No migration required. This is type-only configuration and annotation work. Roll back by reverting the single change set; no data or runtime state is affected.

## PR Strategy

BOT-only, one stacked-to-main PR. Forecast: approximately 35--55 changed lines, well below the supplied 1,500-line review budget. Keep configuration removal, source repairs, inline suppressions, and its regression test atomic: each is required for strict service checking and independently reverting the config would reintroduce the debt. PR description must distinguish source fixes from the four justified stub suppressions and include mypy plus pytest results.

## Open Questions

None.
