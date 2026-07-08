# Proposal: Architecture Debt Reduction

## Intent

`tickets.py` (2015 lines) and `database.py` (1056 lines) are monolithic. Sync Supabase blocks event loop. Custom paginators duplicate `ext.pages`. N+1 queries on member updates. Blocks testability and async correctness.

## Scope

### In Scope
- **PR1** (~80 lines): ticket_note RLS migration, `TTLCache.size`, redundant decorators, `asyncio.gather` backfill
- **PR2** (~120 lines): `acreate_client` + `await` on ~50 `.execute()` calls
- **PR3** (~350 lines): Domain mixins + backward-compatible facade re-export
- **PR4** (~600 lines): Views, embeds, channel creation, close flow extracted
- **PR5** (~200 lines): `ext.pages` migration, `count="exact"`, Postgres RPC

### Out of Scope
- Dashboard, Discord UX, QA/CI, Realtime (fixed in `runtime-bugfixes`)

## Capabilities

### New Capabilities
None — pure refactoring.

### Modified Capabilities
- `database-layer`: Async client, mixin split with facade
- `cache-layer`: `TTLCache.size` property
- `ticket-service`: `create_ticket_channel()`, `close_ticket_full()` extracted
- `ticket-views`: Import path change
- `economy-service`: Postgres RPC for atomic increments

## Approach

**PR1**: Mechanical fixes. RLS migration, `TTLCache.size`, `asyncio.gather`.
**PR2**: HIGH risk. `create_client()` → `acreate_client()`. `await` all `.execute()`. Post-migration grep audit mandatory.
**PR3**: `bot/core/db/` mixins. `database.py` = facade. Depends PR2.
**PR4**: Views, channel creation, close flow extracted to services/utils. tickets.py → ~400 lines.
**PR5**: `_HelpPaginator`/`_ModlogsPaginator` → `ext.pages.Paginator`. RPC `increment_member_field()`.

## Affected Areas

| Area | PR | Impact |
|------|----|--------|
| `migrations/008_ticket_note_rls.sql` | PR1 | New |
| `bot/core/cache.py` | PR1 | Modified |
| `bot/cogs/greetings.py`, `setup.py`, `bot.py` | PR1 | Modified |
| `bot/core/database.py` | PR2, PR3 | Modified |
| `bot/core/db/*.py` | PR3 | New |
| `bot/cogs/tickets.py`, `bot/views/tickets.py` | PR4 | Modified/New |
| `bot/services/ticket_service.py`, `bot/utils/ticket_helpers.py` | PR4 | Modified/New |
| `bot/utils/paginator.py` | PR5 | New |
| `migrations/009_member_increment_rpc.sql` | PR5 | New |

## Risks

| Risk | Likelihood | PR | Mitigation |
|------|------------|----|------------|
| Missed `await` → silent coroutine leak | High | PR2 | Grep audit; mypy |
| DB split breaks imports | Medium | PR3 | Re-export all public names |
| Persistent view paths change | Medium | PR4 | Update `bot.add_view()` |
| RPC bug breaks XP/coins/warnings | Medium | PR5 | Migration + integration tests |

## Rollback Plan

Each PR independently revertable. PR3: delete `bot/core/db/`, restore `database.py`. PR4: move files back. PR5: drop RPC migration.

## Dependencies
- PR3 after PR2; PR5 after PR3; PR1, PR4 independent

## Success Criteria
- [ ] `tickets.py` ≤ 400 lines (from 2015)
- [ ] `database.py` ≤ 30 lines (from 1056)
- [ ] Zero un-awaited `.execute()` calls
- [ ] Zero N+1 member update patterns
- [ ] All tests pass
