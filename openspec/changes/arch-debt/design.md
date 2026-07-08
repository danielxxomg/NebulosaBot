# Design: Architecture Debt Reduction

## Technical Approach

Deliver five review-sized PRs that preserve public bot behavior while moving blocking I/O, monoliths, and duplicated UI logic into testable seams. The current code confirms `Database` is a 42-method Supabase facade with 45 un-awaited database `.execute()` calls, `tickets.py` owns Views plus service logic, and `TTLCache` lives in `bot/core/cache.py` (not `context.py`).

## Architecture Decisions

| Area | Choice | Rationale |
|---|---|---|
| PR1 quick wins | Small mechanical PR: migration 008, `TTLCache.size`, decorator cleanup, bounded startup gather | Low-risk confidence slice before async/database changes. `cache._store` is currently read in `bot/cogs/core.py:139`; public property belongs in `bot/core/cache.py`. |
| PR2 async DB | `__init__` only stores `_url/_key`; async `connect()` creates `_client = await acreate_client(..., AsyncClientOptions(schema="public"))`; type `_client: AsyncClient | None` | Python cannot await factories in `__init__`; this matches existing `create_realtime_client()` and removes sync Supabase calls from async methods. |
| PR3 DB split | `DatabaseBase` + domain mixins + `bot/core/database.py` facade | Keeps `from bot.core.database import Database` stable while reducing a 1056-line file to an import graph. Base owns `__slots__`; mixins define none. |
| PR4 tickets extraction | Move persistent Views to `bot/views/tickets.py`; move command orchestration and helpers into `TicketService`/`bot/utils/ticket_helpers.py`; keep cog command-only | Required to hit `tickets.py <500`: extracting views/channel/close only leaves ~900-1000 lines. Target cog is 350-450 lines. |
| PR5 optimizations | `count="exact"`, RPC member increments, and shared custom `EmbedPaginator` in `bot/utils/paginator.py` | Supabase RPC gives atomic updates and removes get+update races. `discord.ext.pages` is Pycord-only, not available in this discord.py project, so REQ-1 needs spec revision to custom View pagination. |

## Data Flow

```text
Discord command/button -> Cog/View -> TicketService/GuildService -> Database facade
                                      |                         -> db mixin -> AsyncClient
                                      -> Transcript/Discord channel operations
```

Startup backfill:
```text
on_ready -> bounded gather(ensure_guild_exists(guild_id)) -> GuildService -> DB
```

## File Changes

| PR | File | Action | Description |
|---|---|---|---|
| 1 | `migrations/008_ticket_note_rls.sql` | Create | `ALTER TABLE ticket_note ENABLE ROW LEVEL SECURITY;` reproducible/idempotent migration. |
| 1 | `bot/core/cache.py`, `bot/cogs/core.py` | Modify | Add `TTLCache.size`; replace `len(cache._store)` with `cache.size`. |
| 1 | `bot/cogs/greetings.py`, `bot/cogs/setup.py`, `bot/bot.py` | Modify | Remove redundant `@commands.has_permissions`; use `asyncio.gather` with semaphore when `len(guilds) > 50`. |
| 2 | `bot/core/database.py` | Modify | Import `acreate_client`, `AsyncClient`, `AsyncClientOptions`; create client in async `connect()` only; await every database `.execute()`. Tests use `AsyncMock` execute results. |
| 3 | `bot/core/db/{base,guild,member,infraction,ticket,ticket_note,ticket_category,ticket_audit,economy,greeting}_db.py` | Create | Domain mixins using shared `self._client`; preserve `_unwrap` and `_on_write`. |
| 3 | `bot/core/database.py` | Replace | Facade: `class Database(DatabaseBase, GuildDBMixin, MemberDBMixin, ...): pass`. |
| 4 | `bot/views/tickets.py` | Create | Move `TicketPanelView`, `TicketActionsView`, `_CategorySelectView`, `_CategorySelect`; keep `timeout=None` + static `custom_id`. |
| 4 | `bot/utils/embeds.py`, `bot/utils/ticket_helpers.py`, `bot/services/ticket_service.py`, `bot/cogs/tickets.py`, `bot/bot.py` | Modify/Create | Add `build_ticket_embed`, `resolve_ticket_for_channel`, `resolve_ticket_for_reopen`, `resolve_parent_owner`, `create_ticket`, `create_ticket_channel`, `close_ticket_full`, `claim_ticket`, `transfer_ticket`, `create_subticket`, `add_note`, `list_notes`, `deploy_close_panel`, `check_stale_tickets`; update persistent view imports. |
| 5 | `bot/utils/paginator.py`, `bot/cogs/core.py`, `bot/cogs/sentinel.py` | Create/Modify | Add custom `EmbedPaginator(discord.ui.View)` with `previous_button`, `next_button`, `stop_button`, configurable `timeout`, and stable button `custom_id`s; replace `_HelpPaginator` and `_ModlogsPaginator`. Spec revision needed: replace ext.pages REQ-1 with this custom paginator. |
| 5 | `migrations/009_member_increment_rpc.sql`, DB member mixin | Create/Modify | Add `increment_member_xp/coins/warnings` and `set_member_daily`; call via `await self._client.rpc(...).execute()`. |

## Interfaces / Contracts

```python
class Database(DatabaseBase, GuildDBMixin, MemberDBMixin, InfractionDBMixin,
               TicketDBMixin, TicketNoteDBMixin, TicketCategoryDBMixin,
               TicketAuditDBMixin, EconomyDBMixin, GreetingDBMixin):
    pass
```

Existing imports that MUST NOT change: `bot/bot.py`, `bot/core/context.py`, `bot/services/{guild,infraction,ticket,economy,greeting}_service.py`, `tests/conftest.py`, `tests/test_database.py`, `tests/test_realtime.py`, `tests/test_infraction_service.py`.

PR3 slots contract: `DatabaseBase.__slots__ = ("_client", "_url", "_key", "_on_write")`; all domain mixins define no `__slots__` and inherit base state only.

PR4 final cog contract: `tickets.py` keeps only `TicketsCog.__init__`, `cog_load/cog_unload`, `on_message` delegating activity updates, thin command methods (parse args -> call `TicketService` -> send embed), and `auto_close_stale_tickets` delegating to `TicketService.check_stale_tickets()`. The command blocks currently spanning roughly `tickets.py:640-2015` move orchestration into service/helper methods listed above.

PR5 RPC migration contract (quoted camelCase columns, idempotent functions, least privilege grants):

```sql
CREATE OR REPLACE FUNCTION public.increment_member_xp(p_guild_id text, p_user_id text, p_amount integer)
RETURNS TABLE(xp bigint, level integer) LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  RETURN QUERY INSERT INTO public.member ("guildId", "userId", xp, level, coins, warnings, "lastXpGain")
  VALUES (p_guild_id, p_user_id, greatest(p_amount, 0), 0, 0, 0, now())
  ON CONFLICT ("guildId", "userId") DO UPDATE SET xp = greatest(public.member.xp + p_amount, 0), "lastXpGain" = now()
  RETURNING public.member.xp, public.member.level;
END $$;

CREATE OR REPLACE FUNCTION public.increment_member_coins(p_guild_id text, p_user_id text, p_amount integer)
RETURNS TABLE(coins bigint) LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  RETURN QUERY INSERT INTO public.member ("guildId", "userId", xp, level, coins, warnings)
  VALUES (p_guild_id, p_user_id, 0, 0, greatest(p_amount, 0), 0)
  ON CONFLICT ("guildId", "userId") DO UPDATE SET coins = greatest(public.member.coins + p_amount, 0)
  RETURNING public.member.coins;
END $$;

CREATE OR REPLACE FUNCTION public.increment_member_warnings(p_guild_id text, p_user_id text, p_amount integer)
RETURNS TABLE(warnings integer) LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  RETURN QUERY INSERT INTO public.member ("guildId", "userId", xp, level, coins, warnings)
  VALUES (p_guild_id, p_user_id, 0, 0, 0, greatest(p_amount, 0))
  ON CONFLICT ("guildId", "userId") DO UPDATE SET warnings = greatest(public.member.warnings + p_amount, 0)
  RETURNING public.member.warnings;
END $$;

CREATE OR REPLACE FUNCTION public.set_member_daily(p_guild_id text, p_user_id text, p_coin_amount integer, p_streak integer, p_last_daily_reset timestamptz, p_last_daily timestamptz)
RETURNS TABLE(coins bigint, "dailyStreak" integer, "lastDailyReset" timestamptz, "lastDaily" timestamptz) LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  RETURN QUERY INSERT INTO public.member ("guildId", "userId", xp, level, coins, warnings, "dailyStreak", "lastDailyReset", "lastDaily")
  VALUES (p_guild_id, p_user_id, 0, 0, greatest(p_coin_amount, 0), 0, p_streak, p_last_daily_reset, p_last_daily)
  ON CONFLICT ("guildId", "userId") DO UPDATE SET coins = greatest(public.member.coins + p_coin_amount, 0), "dailyStreak" = p_streak, "lastDailyReset" = p_last_daily_reset, "lastDaily" = p_last_daily
  RETURNING public.member.coins, public.member."dailyStreak", public.member."lastDailyReset", public.member."lastDaily";
END $$;

REVOKE ALL ON FUNCTION public.increment_member_xp(text, text, integer), public.increment_member_coins(text, text, integer), public.increment_member_warnings(text, text, integer), public.set_member_daily(text, text, integer, integer, timestamptz, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.increment_member_xp(text, text, integer), public.increment_member_coins(text, text, integer), public.increment_member_warnings(text, text, integer), public.set_member_daily(text, text, integer, integer, timestamptz, timestamptz) TO anon, authenticated, service_role;
```

XP level is still computed in service code from guild economy config thresholds after the RPC returns the new XP; SQL does not encode level rules.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | cache size, decorators, async DB mocks, mixin methods, ticket helpers | Strict TDD with `uv run pytest`; mock Supabase builders with async `execute = AsyncMock(return_value=response)`. |
| Integration | ticket create/close extraction, persistent view imports, RPC SQL shape | Existing Discord mocks; no Discord API calls. |
| Verification | missed awaits, import compatibility, line budgets | Run `uv run mypy bot/`; add `scripts/check_awaited_execute.py` AST verification that flags every `.execute()` call not nested under `ast.Await`; manual checklist for multiline chains, `wc -l bot/cogs/tickets.py`, and `uv run pytest`. |

### Test Migration

PR2 must migrate sync Supabase test doubles to async: `tests/test_database.py` `FakeQueryBuilder.execute()` returns an `AsyncMock`/awaitable response; patches of `create_client` become `acreate_client`; DB fixtures in `tests/conftest.py` and service tests that assert DB calls must await/inspect async mocks. Cache tests touching `_store` (`tests/test_core_cog.py`, `tests/test_ephemeral_standard.py`) must prefer public `cache.size` or cache API outside `bot/core/cache.py`.

## Migration / Rollout

Apply PRs in order: PR1 -> PR2 -> PR3 -> PR4 -> PR5. PR3 follows PR2 to avoid database-file conflicts; PR5 follows PR3 because RPC methods land in member/economy mixins. Each PR is independently revertable. Auto-chain because PR4 and PR3 may exceed the 400-line review budget.

## Open Questions

- [ ] Spec revision needed: update `utility-commands` REQ-1 from `discord.ext.pages.Paginator` to custom `EmbedPaginator` because this project uses `discord.py`, not Pycord.
