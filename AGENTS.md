# NebulosaBot — Code Review Rules — V3

## Python General

- Python 3.11+ — use modern syntax (match/case, `X | Y` unions, `tomllib`)
- Type hints on all public functions and class attributes
- `async`/`await` everywhere — no blocking calls in async context
- Use `dataclasses` for models, not dicts or plain classes
- Prefer `pathlib.Path` over `os.path`
- Use `logging` module, never `print()` for runtime output
- Constants in UPPER_SNAKE_CASE, configurable values in `.env`
- Docstrings on public classes and non-obvious functions (Google style)
- **Function-level imports (PLC0415) are banned by default — stdlib, first-party, and third-party alike.** Allowed ONLY with the canonical inline comment `# noqa: PLC0415 -- <reason>` (matching the per-file ignores in `pyproject.toml`) for exactly three categories: (1) **cycle-break** — hoisting the import would create a module import cycle; (2) **optional-dependency probe** — the import tests whether an optional package exists (e.g. the cairosvg boot probe); (3) **facade indirection** — the function-level import IS a deliberate lazy facade whose symbol is re-exported by that module; mere cycle-avoidance is (1), not (3). Documented carve-out: `scripts/**/*.py` is fully exempt via pyproject per-file ignores. If import order must be frozen, add `# isort: skip` alongside the noqa.

## Discord.py

- All cogs MUST use `async def setup(bot)` (v2.x requirement)
- **Slash-only command surface** (bot-core spec): `get_prefix` resolves to `[]`, zero text-invocable commands. NEW commands MUST use pure app commands (`@app_commands.command()` / `app_commands.Group`), NOT `hybrid_command`
- Legacy `@commands.hybrid_command()` / `@commands.hybrid_group(fallback=...)` declarations MAY remain from earlier cycles — their prefix half is inert because no prefix resolves; do not add new ones
- Persistent views: `timeout=None` + static `custom_id` + `bot.add_view()` on startup
- Background tasks: `@tasks.loop()` with `cog_unload()` to cancel
- Prefix resolution: static empty list (`bot.bot._noop_prefix`) — never consults guild config at invocation time; `GuildConfig.prefix` persists as data only and MUST NOT gate command behavior
- Error handling: application-command errors respond ephemerally; the global handler's only delivery path is a single channel embed via `ctx.send` — NO DM-first branch, no DM fallback (see `ephemeral-standard` spec)
- Never hardcode prefixes, channel IDs, or role IDs — read from guild config. **Documented exception:** `,` survives ONLY as the ticket-channel close-timer trigger parsed by `TicketsCog.on_message`, outside the command framework (`close-confirmation` spec); never reintroduce it as a command prefix
- Use `app_commands.check()` for custom permission checks, compose with `has_permissions()`
- **i18n (100% `t()`)**: ALL user-facing strings — in cogs AND services — MUST go through `t(guild_id, "<key>")`; no hardcoded literals (see `bot/core/i18n.py`; every `t()` literal must exist in `bot/locales/{es,en}.json`; scan via `tests/test_i18n_key_coverage.py`)
- **Permission decorators**: `@can_check("<perm>")` (matrix-gated, 7 keys: `moderation.{warn,mute,kick,ban}`, `tickets.manage`, `economy.manage`, `greeting.manage`); `@is_mod()` (mod-role fallback); `@is_admin()` (admin-only). All three dual-register prefix+slash. Use `can()`/`can_member()` for non-decorator call sites
- **Command visibility**: admin/config → ephemeral; mod-action → permanent; fun → permanent (including ocio `/dice`, `/banana`, `/8ball` — permanent per `ocio-commands` spec, zero DB writes); personal/info → ephemeral (see `ephemeral-standard` spec)
- **Background loops**: `@tasks.loop()` MUST be DB-sourced for restart durability (scan each iteration, no in-memory timers), with `before_loop` (wait ready) + `cog_unload()` (cancel)
- Sync tree: `await tree.sync()` in `setup_hook()`, not in `on_ready()`

## Architecture

- **Cogs** handle Discord interaction only — no business logic
- **Services** handle business logic + cache integration — testable without Discord mocks
- **Models** are dataclasses mirroring DB rows — no ORM
- **Cache-first reads**: check RAM cache → DB fallback → populate cache
- **Guild-scoped keys**: cache keys MUST include guild_id (e.g., `{guild_id}:config`); new caches MUST use `cache_key(guild_id, entity)` from `bot.core.cache` so keys are `{guild_id}:{entity}` and cannot leak across guilds
- **No blocking I/O in event loop**: use `asyncio.to_thread()` for Pillow, file I/O, etc.
- **Supabase**: `create_client()` with `AsyncClientOptions(schema="public", auto_refresh_token=False, persist_session=False)`; async is MUST
- **Renderer**: `Pillow` is the default (procedural, `brand.ACCENT`); `cairosvg` optional behind a boot probe (`ImportError` → WARNING + Pillow injection). Do NOT hard-depend on `cairosvg`
- **Listeners observe + delegate, never mutate**: `bot/listeners/*.py` cogs MUST NOT kick/mute/move/DM/send-into-voice and MUST NOT perform Discord mutations directly. They observe + log via `LoggingService`; any sanctioned Discord mutation (e.g. level-reward `add_roles`) goes through a service method (`EconomyService.assign_level_role`). Moderation-class mutations from listeners are NEVER allowed. Per-member debounce is guild-scoped (`f"{guild_id}:{member_id}"`) with TTL + stale eviction

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
- Migrations: DDL MUST use `IF NOT EXISTS` (`ADD COLUMN IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`) for idempotent live re-runs; check via `tests/test_migrations.py`

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
- ❌ Using `is_mod()`/`is_admin()` when `can_check()` applies (matrix-gated permissions)
- ❌ Listeners that mutate state (kick/mute/move/DM) — listeners are read-only
- ❌ Hardcoded user-facing strings in cogs — use `t(guild_id, "<key>")`
- ❌ Hand-built guild-scoped cache keys — use `cache_key(guild_id, entity)` from `bot.core.cache`
- ❌ DDL without `IF NOT EXISTS` — migrations must guard `ADD COLUMN`/`CREATE INDEX`

## GGA Review Discipline

These rules bind the Gentleman Guardian Angel (GGA) reviewer so strict
mode blocks only on real AGENTS.md violations, not on opinion or
inherited debt.

- **Cite the rule**: every blocking violation MUST cite the specific
  AGENTS.md section or bullet it violates. Stylistic suggestions,
  framework-idiom preferences, and "consider X" advice that do not map
  to an explicit AGENTS.md rule are non-blocking observations, not
  failures.
- **Scope to the diff**: blocking violations MUST be in lines added or
  modified by the commit. Pre-existing issues in untouched code of a
  file the diff happens to touch are tech-debt notes to file for a
  later pass, not commit blockers.
- **No false positives**: before blocking, verify the claimed
  violation against the actual code at the cited location. If the code
  already conforms (e.g. return type hints present, error_embed used),
  the violation is invalid and must not block.
- **Bundled scope ok**: a restoration/scoping commit that wires in
  previously-uncommitted artifacts is judged only on the artifacts it
  restores plus the wiring lines — not on adjacent pre-existing debt.

## Domain Notes

- **`/unclaim` gate is claimer-or-mod in the service — matrix-gate intentionally absent**: authorization lives in `TicketService.check_can_unclaim` (claimer OR mod role; raises on violation), NOT in a `can_check()`/`@is_mod()` decorator. This is deliberate: the gate depends on ticket state (`claimedBy`), not just the caller's permission key. Guard test: `tests/test_tickets_cog.py::TestUnclaimCommand::test_unclaim_not_gated_by_is_mod`. Do not "fix" by adding a matrix key.
- **`bot/utils/time.py` vs `bot/utils/timeparse.py` — DO NOT MERGE**: `time.py` parses human duration strings → seconds (Sentinel timeouts); `timeparse.py` parses DB timestamp values → `datetime` (economy). Different domains, different callers. Keep separate and document the other as a distinct domain.
- **Brand tokens**: all colors via `bot/utils/brand.py` (`ACCENT`, `INFO`, etc.); no hex literals outside `brand.py`. Greeting accent is `brand.ACCENT`, not `GREETING_ACCENT`/`#7289da`.
