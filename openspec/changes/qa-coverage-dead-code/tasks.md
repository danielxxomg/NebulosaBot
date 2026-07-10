# Tasks: QA Coverage & Dead Code Cleanup (Cycle 2)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~990 (3 stacked PRs) |
| 400-line budget risk | High (exceeds default 400) |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 (stacked-to-main) |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Model + brand + help + manual tests (zero production changes) | PR 1 → main | Pure tests; green immediately |
| 2 | DB facade contract fixes + updated/new facade tests | PR 2 → main | Production: Member.from_db_row, 2 facades, 2 call sites; tests updated |
| 3 | Sentinel behavior tests | PR 3 → main | New file; mock service/member boundaries |

---

## Phase 1: Model Contract Fixes & Tests (PR 1)

- [x] 1.1 [RED] Create `tests/test_economy_config_model.py` — test `from_db_row` with all fields, `to_db_dict` round-trip, defaults for missing keys. Ver: `uv run pytest tests/test_economy_config_model.py -x`
- [x] 1.2 [RED] Create `tests/test_member_model.py` — test `from_db_row` current behavior (strings pass through), `to_db_dict` serializes datetime to ISO, defaults for optional fields. **PR1 deviation**: tests current behavior, not datetime parsing — production fix deferred to PR2. Ver: `uv run pytest tests/test_member_model.py -x`
- [ ] 1.3 [GREEN] Fix `bot/models/member.py` — in `from_db_row`, parse `lastDailyReset`, `lastDaily`, `lastXpGain` with `datetime.fromisoformat()` when value is a string. **DEFERRED TO PR2** per orchestrator boundary.

## Phase 2: Brand Contract & Hex Scan (PR 1)

- [x] 2.1 [GREEN] Extend `tests/test_brand.py` — add test scanning `bot/**/*.py` (excluding `brand.py`) for hardcoded `#[0-9A-Fa-f]{6}` hex in embed color assignments. Ver: `uv run pytest tests/test_brand.py -x`

## Phase 3: Help Builder Tests (PR 1)

- [x] 3.1 [RED] Create `tests/test_core_help_builder.py` — test `_build_cog_help_embed` returns embed for visible commands, None for empty/missing cog; `_build_help_pages` produces one page per cog with commands; `_resolve_prefix` reads guild config or falls back. Mock bot with cogs. Ver: `uv run pytest tests/test_core_help_builder.py -x`

## Phase 4: Manual Dynamic Discovery Test (PR 1)

- [x] 4.1 [RED] Extend `tests/test_manual.py` — discover `@hybrid_command` decorators from imported cog classes, assert each command name appears in `docs/MANUAL.md` with description. Alphabetical sort for order resilience. Ver: `uv run pytest tests/test_manual.py -k dynamic_discovery -x`

## Phase 5: PR 1 Verification

- [x] 5.1 Run `uv run pytest` — all green, `-W error`. Run `uv run ruff check .` and `uv run mypy bot`. Commit: `test(qa): add model, brand hex-scan, help builder, and manual discovery tests`

---

## Phase 6: Member Datetime Contract Fix (PR 2)

- [x] 6.1 [GREEN] Verify `bot/models/member.py` — `from_db_row` parses ISO strings for `lastDailyReset`, `lastDaily`, `lastXpGain` via `datetime.fromisoformat()`. Already done in 1.3; confirm tests pass. Ver: `uv run pytest tests/test_member_model.py -x`

## Phase 7: DB Facade Contract Corrections (PR 2)

- [x] 7.1 [GREEN] Fix `bot/core/db/ticket_category_db.py` — add `guild_id: str` param to `count_open_tickets_by_category(self, guild_id, category_id)`, add `.eq("guildId", guild_id)` filter. Ver: sig matches `(self, guild_id, category_id)`
- [x] 7.2 [GREEN] Fix `bot/core/db/infraction_db.py` — add `guild_id: str` param to `deactivate_infraction(self, guild_id, infraction_id)`, add `.eq("guildId", guild_id)` filter. Ver: sig matches `(self, guild_id, infraction_id)`
- [x] 7.3 [GREEN] Fix `bot/cogs/tickets.py` line 283 — pass `guild_id` to `count_open_tickets_by_category(guild_id, category_id)`. Ver: call site matches new signature
- [x] 7.4 [GREEN] Fix `bot/services/infraction_service.py` line 95 — pass `guild_id` to `deactivate_infraction(guild_id, infraction_id)`. Ver: `unwarn()` passes guild_id through

## Phase 8: Update Existing Tests for New Signatures (PR 2)

- [x] 8.1 [GREEN] Update `tests/conftest.py` — `mock_db.count_open_tickets_by_category` and `mock_db.deactivate_infraction` still AsyncMock (signatures don't affect mocks). Confirm no changes needed.
- [x] 8.2 [GREEN] Update `tests/test_database.py::TestCountOpenTicketsByCategory` — pass `guild_id` to all `count_open_tickets_by_category` calls, assert `("eq", "guildId", guild_id)` in filters. Ver: `uv run pytest tests/test_database.py::TestCountOpenTicketsByCategory -x`
- [x] 8.3 [GREEN] Update `tests/test_tickets_cog.py` — update `count_open_tickets_by_category` mock calls to expect `guild_id` arg. Ver: `uv run pytest tests/test_tickets_cog.py -x`
- [x] 8.4 [GREEN] Update `tests/test_infraction_service.py` — update `deactivate_infraction` mock calls to expect `guild_id` arg. Ver: `uv run pytest tests/test_infraction_service.py -x`
- [x] 8.5 [GREEN] Update `tests/test_sentinel_cog.py` — update `deactivate_infraction` mock calls to expect `guild_id` arg. Ver: `uv run pytest tests/test_sentinel_cog.py -x`

## Phase 9: New DB Facade Tests (PR 2)

- [x] 9.1 [RED] Create `tests/test_ticket_category_db.py` — test `count_open_tickets_by_category(guild_id, cat_id)` returns exact count with `guildId` filter; `update_ticket_category_field_definitions` filters by both `id` and `guildId`. Ver: `uv run pytest tests/test_ticket_category_db.py -x`
- [x] 9.2 [RED] Create `tests/test_ticket_db.py` — test `get_stale_tickets` filters by time threshold, `get_open_ticket_channel_ids` extracts channel IDs, `update_ticket_last_activity` updates by channel. Ver: `uv run pytest tests/test_ticket_db.py -x`
- [x] 9.3 [RED] Create `tests/test_greeting_db.py` — test `upsert_greeting_config` persists and fires `_on_write`. Ver: `uv run pytest tests/test_greeting_db.py -x`
- [x] 9.4 [RED] Create `tests/test_infraction_db.py` — test `deactivate_infraction(guild_id, id)` sets `active=false` with `guildId` filter. Ver: `uv run pytest tests/test_infraction_db.py -x`

## Phase 10: PR 2 Verification

- [x] 10.1 Run `uv run pytest` — all green. Run `uv run ruff check .` and `uv run mypy bot`. Commit: `fix(db): guild-scope facade methods + model datetime parsing + facade tests`

---

## Phase 11: Sentinel Behavior Tests (PR 3)

- [ ] 11.1 [RED] Create `tests/test_sentinel_behavior.py` — test `warn` calls `infraction_service.warn()` + logs moderation; test warn auto-escalation triggers mute; test `mute` calls `member.timeout()`; test `kick`/`ban` send ConfirmCancelView; test `_validate_target` denies self-target, higher-role target, bot target. Mock services/member/logging. Ver: `uv run pytest tests/test_sentinel_behavior.py -x`

## Phase 12: PR 3 Verification

- [ ] 12.1 Run `uv run pytest` — all green. Run `uv run ruff check .` and `uv run mypy bot`. Commit: `test(qa): add sentinel behavior tests for warn/mute/kick/validate_target`
