# Tasks: Architecture Debt Reduction

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines (total) | ~1350 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 → PR 4 → PR 5 |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Quick wins: cache, decorators, gather, RLS migration | PR 1 | ~80 lines; independent; LOW risk |
| 2 | Async Supabase client + await all execute | PR 2 | ~120 lines; independent; HIGH risk |
| 3 | DB split: domain mixins + facade | PR 3 | ~350 lines; after PR2; MEDIUM risk |
| 4 | tickets.py extraction: views, service, helpers | PR 4 | ~600 lines; independent; MEDIUM risk |
| 5 | Shared utils + RPC optimizations | PR 5 | ~200 lines; after PR3; LOW-MED risk |

## Phase 1: PR1 — Quick Wins (~80 lines, LOW risk)

- [x] 1.1 [RED] Write test for `TTLCache.size` property in `tests/test_core_cache.py` — assert `cache.size == 0` on empty, `cache.size == N` after N inserts. Ver: `uv run pytest tests/test_core_cache.py -k test_cache_size -x`
- [x] 1.2 [GREEN] Add `@property def size(self) -> int` to `TTLCache` in `bot/core/cache.py`. Update `bot/cogs/core.py:139` to use `cache.size` instead of `len(cache._store)`. Ver: `uv run pytest tests/test_core_cache.py tests/test_core_cog.py -x`
- [x] 1.3 [RED] Write test in `tests/test_bot_startup.py` — mock `ensure_guild_exists`, verify all guilds backfilled concurrently (assert call count == guild count). Ver: `uv run pytest tests/test_bot_startup.py -k test_on_ready_gather -x`
- [x] 1.4 [GREEN] Replace sequential `await` loop in `bot/bot.py` `on_ready` with `asyncio.gather(*[...], return_exceptions=True)` for guild backfill. Add semaphore (>50 guilds). Ver: `uv run pytest tests/test_bot_startup.py -x`
- [x] 1.5 [GREEN] Remove redundant `@commands.has_permissions(administrator=True)` from `bot/cogs/greetings.py` (`/welcome_test`, `/goodbye_test`) and `bot/cogs/setup.py` (`/setup`). Keep `@is_admin()`. Ver: `uv run ruff check bot/cogs/greetings.py bot/cogs/setup.py`
- [x] 1.6 [GREEN] Create `migrations/008_ticket_note_rls.sql` with `ALTER TABLE ticket_note ENABLE ROW LEVEL SECURITY;` (idempotent). Ver: `uv run pytest tests/ -x` (no test regressions)
- [x] 1.7 Verify PR1: `uv run pytest && uv run ruff check bot/ && uv run mypy bot/`

## Phase 2: PR2 — Async Supabase (~120 lines, HIGH risk)

- [x] 2.1 [RED] Update `tests/test_database.py` — change `FakeQueryBuilder.execute()` to return `AsyncMock(return_value=response)`. Patch `create_client` → `acreate_client`. Ver: `uv run pytest tests/test_database.py -x` (should fail — sync execute no longer works)
- [x] 2.2 [GREEN] In `bot/core/database.py`: import `acreate_client`, `AsyncClient`, `AsyncClientOptions`. Change `connect()` to `await acreate_client(...)`. Update type hint `self._client: AsyncClient | None`. Ver: `uv run pytest tests/test_database.py -x`
- [x] 2.3 [GREEN] Add `await` to all ~45 `.execute()` calls in `bot/core/database.py` (every method that calls `self._client.table(...).execute()`). Ver: `uv run pytest tests/test_database.py tests/test_*.py -x`
- [x] 2.4 [REFACTOR] Create `scripts/check_awaited_execute.py` — AST walker that flags every `.execute()` call not under `ast.Await`. Run: `uv run python scripts/check_awaited_execute.py bot/core/database.py`. Fix any flagged calls.
- [x] 2.5 [GREEN] Run `uv run mypy bot/core/database.py` — catches unawaited coroutines. Fix any errors. Ver: `uv run mypy bot/`
- [x] 2.6 Verify PR2: `uv run pytest && uv run mypy bot/ && uv run python scripts/check_awaited_execute.py bot/core/database.py` (zero misses)

## Phase 3: PR3 — DB Split: Mixin + Facade (~350 lines, MEDIUM risk)

- [ ] 3.1 [GREEN] Create `bot/core/db/__init__.py` (empty), `bot/core/db/base.py` with `DatabaseBase` class: `__slots__ = ('_client', '_url', '_key', '_on_write')`, properties for `_client` access, `_unwrap()` static, `_on_write()` method.
- [ ] 3.2 [GREEN] Create `bot/core/db/guild_db.py` — `GuildDBMixin(DatabaseBase)` with `get_guild`, `upsert_guild`, `ensure_guild_exists`, `update_guild_panel` (4 methods). Methods moved from `database.py`. Mixin defines NO `__slots__`.
- [ ] 3.3 [GREEN] Create `bot/core/db/member_db.py` — `MemberDBMixin(DatabaseBase)` with `get_member`, `update_member_warnings` (2 methods).
- [ ] 3.4 [GREEN] Create `bot/core/db/infraction_db.py` — `InfractionDBMixin(DatabaseBase)` with `insert_infraction`, `get_infractions`, `get_active_warnings`, `deactivate_infraction` (4 methods).
- [ ] 3.5 [GREEN] Create `bot/core/db/ticket_db.py` — `TicketDBMixin(DatabaseBase)` with `insert_ticket`, `get_ticket`, `get_ticket_by_channel`, `get_ticket_by_number`, `get_tickets_by_parent`, `update_ticket`, `get_stale_tickets`, `get_max_ticket_number`, `get_open_ticket_channel_ids`, `update_ticket_last_activity` (10 methods).
- [ ] 3.6 [GREEN] Create `bot/core/db/ticket_note_db.py` — `TicketNoteDBMixin` with `insert_ticket_note`, `get_ticket_notes`, `delete_ticket_note`, `get_recent_notes_for_dedup` (4 methods).
- [ ] 3.7 [GREEN] Create `bot/core/db/ticket_category_db.py` — `TicketCategoryDBMixin` with `insert_ticket_category`, `get_ticket_categories`, `get_ticket_category`, `delete_ticket_category`, `count_open_tickets_by_category` (5 methods).
- [ ] 3.8 [GREEN] Create `bot/core/db/ticket_audit_db.py` — `TicketAuditDBMixin` with `insert_audit_row`, `get_audit_rows` (2 methods).
- [ ] 3.9 [GREEN] Create `bot/core/db/economy_db.py` — `EconomyDBMixin` with `get_economy_config`, `upsert_economy_config`, `update_member_xp`, `update_member_coins`, `update_member_daily`, `get_leaderboard`, `get_member_rank` (7 methods).
- [ ] 3.10 [GREEN] Create `bot/core/db/greeting_db.py` — `GreetingDBMixin` with `get_greeting_config`, `upsert_greeting_config` (2 methods).
- [ ] 3.11 [GREEN] Replace `bot/core/database.py` with facade: `from bot.core.db.base import DatabaseBase; from bot.core.db.guild_db import GuildDBMixin; ...; class Database(DatabaseBase, GuildDBMixin, MemberDBMixin, InfractionDBMixin, TicketDBMixin, TicketNoteDBMixin, TicketCategoryDBMixin, TicketAuditDBMixin, EconomyDBMixin, GreetingDBMixin): pass`. Re-export all public names.
- [ ] 3.12 [RED] Write import test in `tests/test_database.py` — `from bot.core.database import Database` works; `Database()` has all 42 methods (`hasattr` check). Ver: `uv run pytest tests/test_database.py -k test_database_import -x`
- [ ] 3.13 Verify PR3: `uv run pytest && uv run mypy bot/ && grep -r "from bot.core.db\." bot/ | grep -v "from bot.core.database"` (no direct mixin imports outside database.py)

## Phase 4: PR4 — tickets.py Extraction (~600 lines, MEDIUM risk)

- [ ] 4.1 [GREEN] Create `bot/views/tickets.py` — move `TicketPanelView`, `TicketActionsView`, `_CategorySelectView`, `_CategorySelect` from `bot/cogs/tickets.py`. Keep `timeout=None` + static `custom_id`. Preserve all imports.
- [ ] 4.2 [GREEN] Add `build_ticket_embed()` to `bot/utils/embeds.py` — moved from `_build_ticket_embed` in `tickets.py`. Uses `COLOR_INFO`, `COLOR_SUCCESS`, `t()`.
- [ ] 4.3 [GREEN] Create `bot/utils/ticket_helpers.py` — add `resolve_ticket_for_channel(bot, channel_id, guild_id, action) -> dict | None`. Dedupes 7 lookup locations in tickets.py.
- [ ] 4.4 [GREEN] Add to `bot/services/ticket_service.py`: `create_ticket_channel(guild, author, category_id, guild_config, mod_role)` — extracts channel creation logic from `_CategorySelect.callback` and `subticket_create` (deduped).
- [ ] 4.5 [GREEN] Add to `bot/services/ticket_service.py`: `close_ticket_full(guild, ticket, bot)` — extracts close flow from `_close_one_ticket` and `TicketActionsView.close_button`.
- [ ] 4.6 [GREEN] Add to `bot/services/ticket_service.py`: `create_ticket`, `close_ticket`, `claim_ticket`, `transfer_ticket`, `create_subticket`, `add_note`, `list_notes`, `deploy_panel`, `check_stale_tickets` (delegate thin wrappers where not already present).
- [ ] 4.7 [GREEN] Update `bot/bot.py` `setup_hook` — change `add_view` imports from `bot.cogs.tickets` to `bot.views.tickets`. Ver: bot startup does not error.
- [ ] 4.8 [REFACTOR] Shrink `bot/cogs/tickets.py` — keep ONLY: `TicketsCog` class, `__init__`, `cog_load/cog_unload`, `on_message` (delegating to service), thin command definitions (parse args → call `TicketService` → send embed), `auto_close` task (delegating to service). Target: 350–450 lines.
- [ ] 4.9 [RED] Write test in `tests/test_tickets_extraction.py` — `wc -l bot/cogs/tickets.py` < 500. Also: `from bot.views.tickets import TicketPanelView, TicketActionsView` works. Ver: `uv run pytest tests/test_tickets_extraction.py -x`
- [ ] 4.10 [RED] Write tests for each new `TicketService` method (`create_ticket_channel`, `close_ticket_full`, `resolve_ticket_for_channel`) using existing Discord mocks. Ver: `uv run pytest tests/test_ticket_service.py -x`
- [ ] 4.11 Verify PR4: `uv run pytest && wc -l bot/cogs/tickets.py` (< 500) && `uv run ruff check bot/views/tickets.py bot/services/ticket_service.py`

## Phase 5: PR5 — Shared Utils + DB Optimizations (~200 lines, LOW-MED risk)

- [ ] 5.1 [GREEN] Create `bot/utils/paginator.py` — `EmbedPaginator(discord.ui.View)` with `previous_button`, `next_button`, `stop_button`, configurable `timeout`, stable `custom_id`s for persistence. Replaces `_HelpPaginator` and `_ModlogsPaginator`.
- [ ] 5.2 [GREEN] Replace `_HelpPaginator` in `bot/cogs/core.py` with `EmbedPaginator`. Ver: `uv run pytest tests/test_core_cog.py -x`
- [ ] 5.3 [GREEN] Replace `_ModlogsPaginator` in `bot/cogs/sentinel.py` with `EmbedPaginator`. Ver: `uv run pytest tests/test_sentinel.py -x`
- [ ] 5.4 [RED] Write test in `tests/test_database.py` — `count_open_tickets_by_category` returns count without fetching rows (mock verify: `execute` called once, `response.count` used, not `len(response.data)`). Ver: `uv run pytest tests/test_database.py -k test_count_exact -x`
- [ ] 5.5 [GREEN] Fix `count_open_tickets_by_category` in `bot/core/db/ticket_category_db.py` — use `count="exact"` on select, read `response.count`. Ver: `uv run pytest tests/test_database.py -k test_count_exact -x`
- [ ] 5.6 [GREEN] Create `migrations/009_member_increment_rpc.sql` with 4 PL/pgSQL functions: `increment_member_xp`, `increment_member_coins`, `increment_member_warnings`, `set_member_daily` — `SECURITY DEFINER`, quoted camelCase columns, `ON CONFLICT` upsert, `REVOKE`/`GRANT` for least privilege.
- [ ] 5.7 [RED] Write tests in `tests/test_database.py` — RPC `increment_member_xp` returns updated value in 1 call (mock `_client.rpc(...).execute()`); upsert creates row on first call. Ver: `uv run pytest tests/test_database.py -k test_rpc_increment -x`
- [ ] 5.8 [GREEN] Replace get+update N+1 pattern in 4 `MemberDBMixin`/`EconomyDBMixin` methods (`update_member_xp`, `update_member_coins`, `update_member_warnings`, `update_member_daily`) with `.rpc()` calls. Ver: `uv run pytest tests/test_database.py tests/test_economy_service.py -x`
- [ ] 5.9 Verify PR5: `uv run pytest && uv run ruff check bot/ && uv run mypy bot/`

---

**Total tasks**: 40 | **RED (test-first) tasks**: 11 | **GREEN (implement) tasks**: 23 | **REFACTOR tasks**: 2 | **Verify tasks**: 5
