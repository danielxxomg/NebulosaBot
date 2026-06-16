# NebulosaBot — Code Review Rules

## Python General

- Python 3.11+ — use modern syntax (match/case, `X | Y` unions, `tomllib`)
- Type hints on all public functions and class attributes
- `async`/`await` everywhere — no blocking calls in async context
- Use `dataclasses` for models, not dicts or plain classes
- Prefer `pathlib.Path` over `os.path`
- Use `logging` module, never `print()` for runtime output
- Constants in UPPER_SNAKE_CASE, configurable values in `.env`
- Docstrings on public classes and non-obvious functions (Google style)

## Discord.py

- All cogs MUST use `async def setup(bot)` (v2.x requirement)
- Use `@commands.hybrid_command()` for user-facing commands (prefix + slash)
- Use `@commands.hybrid_group(fallback=...)` for command groups
- Persistent views: `timeout=None` + static `custom_id` + `bot.add_view()` on startup
- Background tasks: `@tasks.loop()` with `cog_unload()` to cancel
- Prefix resolution: always async callable reading from cache-first guild config
- Error handling: ephemeral embeds for slash, channel embeds for prefix
- Never hardcode prefixes, channel IDs, or role IDs — read from guild config
- Use `app_commands.check()` for custom permission checks, compose with `has_permissions()`
- Sync tree: `await tree.sync()` in `setup_hook()`, not in `on_ready()`

## Architecture

- **Cogs** handle Discord interaction only — no business logic
- **Services** handle business logic + cache integration — testable without Discord mocks
- **Models** are dataclasses mirroring DB rows — no ORM
- **Cache-first reads**: check RAM cache → DB fallback → populate cache
- **Guild-scoped keys**: cache keys MUST include guild_id (e.g., `{guild_id}:config`)
- **No blocking I/O in event loop**: use `asyncio.to_thread()` for Pillow, file I/O, etc.
- **Supabase**: use `create_client()` with `ClientOptions`, async operations preferred

## Naming

- Files/modules: `snake_case` (e.g., `guild_service.py`)
- Classes: `PascalCase` (e.g., `GuildService`, `NebulosaBot`)
- Functions/methods: `snake_case` (e.g., `get_config`, `on_guild_join`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `DEFAULT_PREFIX`, `CACHE_TTL`)
- Private: prefix with `_` (e.g., `_internal_method`)
- Cog names: descriptive (e.g., `CoreCog`, `SentinelCog`)

## Error Handling

- All commands MUST handle errors gracefully — no raw tracebacks to users
- Use `error_embed()`, `success_embed()`, `info_embed()` from `bot/utils/embeds.py`
- Log full exceptions with `logging.exception()` or `logger.error(..., exc_info=True)`
- Permission errors: clear message telling the user what permission is missing
- Cooldown errors: tell the user how long to wait

## Database

- Always filter by `guild_id` in multi-guild queries
- Application-level FK validation (Supabase Transaction Mode has no FK enforcement)
- Idempotent operations — double-click must not create duplicates
- Soft deletes for Guild (`active` flag), hard deletes only when explicitly required

## Testing

- pytest + pytest-asyncio
- Mock Discord objects (Member, Interaction, Guild) — never call Discord API in tests
- Test cache-first logic: hit path, miss path, invalidation
- Test permission checks: admin, mod, regular user, unconfigured
- Each test should be independent — no shared mutable state

## Anti-patterns (reject in review)

- ❌ `print()` instead of `logging`
- ❌ Hardcoded IDs (guild, channel, role)
- ❌ Blocking calls in async functions (`time.sleep`, `requests`, `Pillow` without `to_thread`)
- ❌ Business logic inside cog command handlers — extract to services
- ❌ Missing `guild_id` filter on database queries
- ❌ Using `on_ready` for cog loading or tree sync
- ❌ `timeout=None` without `custom_id` on persistent views
- ❌ Bare `except:` — always catch specific exceptions
