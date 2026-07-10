# Design: QA Coverage & Dead Code Cleanup (Cycle 2)

## Technical Approach

Add deterministic pytest coverage around the current public model, database-facade, cog-helper, brand, and documentation contracts. Reuse the established async mocks and `FakeSupabaseClient` rather than contacting Discord or Supabase. This implements the six delta specs while avoiding duplicate tests where equivalent coverage already exists in `tests/test_database.py`, `tests/test_sentinel_cog.py`, and `tests/test_brand.py`.

## Architecture Decisions

| Decision | Alternatives / tradeoff | Rationale |
|---|---|---|
| Extend existing focused suites | Create every proposed new test file | Existing suites already own DB facade, Sentinel behavior, and brand exports; extending them preserves shared fixtures and avoids duplicate assertions. |
| Keep `FakeSupabaseClient` query-recording only | Build an in-memory Supabase emulator | It already records filters, mutations, and `count="exact"`; assert query contracts plus returned fixtures. Emulating predicate execution would duplicate Supabase behavior. |
| Test commands from cog class metadata | Start/load a real bot | Inspect imported cog classes and recursively walk their command objects; this is deterministic and needs no Discord connection or cog load order. |
| RED tests before contract corrections | Relax specs to current signatures | The Member datetime and DB scope requirements do not match current code, so tests must expose the gap before minimal production fixes. |

## Data Flow

```text
pytest test -> Database facade -> FakeSupabaseClient -> recorded query / fixture response
pytest test -> Cog callback/helper -> AsyncMock Discord/services -> asserted calls/embed/view
pytest test -> Cog command metadata -> normalized command names -> docs/MANUAL.md
```

## File Changes

| File | Action | Description |
|---|---|---|
| `tests/test_economy_config_model.py` | Create | EconomyConfig round-trip and defaults. |
| `tests/test_member_model.py` | Create | Member datetime parsing/ISO serialization and defaults. |
| `tests/test_database.py` | Modify | Add missing facade query/mutation assertions using its local fake. |
| `tests/test_sentinel_cog.py` | Modify | Add missing auto-escalation and bot-target behavior without duplicating existing happy-path tests. |
| `tests/test_core_help_builder.py` | Create | Internal help builders and context-prefix fallback. |
| `tests/test_brand.py` | Modify | Add production-source hex-literal contract scan. |
| `tests/test_manual.py` | Modify | Add order-independent runtime command discovery assertion. |
| `bot/models/member.py` | Modify | Parse DB ISO datetime strings before `to_db_dict()` serializes them. |
| `bot/core/db/ticket_category_db.py` | Modify | Align count method with guild-scoped facade contract if retained by the delta. |
| `bot/core/db/ticket_db.py` | Modify | Align last-activity signature/filter with the guild- and timestamp-scoped delta. |
| `bot/core/db/infraction_db.py` | Modify | Align soft-delete with the guild-scoped delta. |
| `bot/cogs/tickets.py` | Modify | Pass newly required guild/timestamp facade arguments. |
| `bot/services/infraction_service.py` | Modify | Pass guild ID to guild-scoped deactivation. |

## Interfaces / Contracts

`FakeQueryBuilder` already supports `select(count="exact")`, `eq`, `in_`, `lt`, `gte`, `update`, `upsert`, and recorded filters. No extension is required. Tests must inspect `get_table_filters()` and `get_table_calls()`; fixture rows represent Supabase responses rather than locally filtered data.

The delta signatures conflict with the live interfaces. Implement the scoped contracts as:

```python
async def count_open_tickets_by_category(self, guild_id: str, category_id: str) -> int: ...
async def update_ticket_last_activity(self, guild_id: str, channel_id: str, timestamp: str) -> None: ...
async def deactivate_infraction(self, guild_id: str, infraction_id: str) -> None: ...
```

`Member.from_db_row()` must convert non-null ISO strings for all three datetime fields with `datetime.fromisoformat`; already-constructed datetimes remain accepted.

## Testing Strategy

| Layer | What to test | Approach |
|---|---|---|
| Unit | Models, help builders, brand scan, command discovery | Pure rows/mocks; inspect embeds and normalized command sets. |
| Facade | Six target DB operations | Async `Database` with local fake; assert values, writes, and every required `guildId` filter. |
| Cog behavior | Warn escalation, mute, confirmations, invalid targets | Call hybrid `.callback`; mock service/member/logging boundaries, never locale text. |
| Regression | Full suite and quality gates | `uv run pytest`, then `uv run ruff check .` and `uv run mypy bot`. No E2E layer exists. |

Strict TDD order: write failing model/contract tests, make the smallest production correction, then add pure helper, documentation, and behavioral regressions.

## Migration / Rollout

No data migration. DB facade signature changes are internal but require atomic call-site updates. Deliver as stacked slices to main: (1) models/brand/help/manual, (2) facade contract corrections plus tests, (3) Sentinel behavior. This likely exceeds the 400-line review budget despite the requested 1500-line budget.

## Open Questions

- [ ] The proposal says test-only, but current `Member` and three facade contracts cannot satisfy the delta without the listed production changes. Confirm that these minimal corrections remain in scope before apply.
