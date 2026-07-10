## Exploration: qa-coverage-dead-code (Cycle 2 of hygiene program)

### Current State

**Baseline after cycle 1**: 1272 tests, 0 warnings, `-W error` green, ruff/mypy clean, load resilience done.

**Coverage gaps identified**:
- `bot/models/economy_config.py` — 0% coverage (dataclass with `from_db_row`/`to_db_dict`)
- `bot/models/member.py` — 0% coverage (dataclass with `from_db_row`/`to_db_dict`, datetime fields)
- `bot/__main__.py` — 0% coverage (entry point, `main()` bootstrap)
- `bot/core/db/ticket_category_db.py` — ~49% coverage (5 methods, some untested)
- `bot/core/db/ticket_db.py` — ~62% coverage (10 methods, `get_stale_tickets`, `get_open_ticket_channel_ids`, `update_ticket_last_activity` untested)
- `bot/core/db/greeting_db.py` — low coverage (2 methods, `upsert_greeting_config` untested)
- `bot/core/db/infraction_db.py` — low coverage (4 methods, `deactivate_infraction` untested via facade)
- `bot/cogs/sentinel.py` — behavior tests exist but focus on i18n; happy-path behavioral coverage needed
- `bot/cogs/core.py` — help builder (`_build_cog_help_embed`, `_build_help_pages`) untested
- `bot/utils/brand.py` — PRIMARY/ACCENT defined but **never imported** by production code (only INFO, SUCCESS, ERROR, WARNING used)
- `docs/MANUAL.md` — Spanish manual exists, tests check headings/commands but not dynamic hybrid command discovery

### Affected Areas

- `bot/models/economy_config.py` — Pure dataclass, easy to test (round-trip, defaults, edge cases)
- `bot/models/member.py` — Pure dataclass with datetime fields, easy to test
- `bot/__main__.py` — Entry point; testing `main()` requires mocking `BotConfig.from_env()` + `NebulosaBot` + `bot.start()`
- `bot/core/db/ticket_category_db.py` — `count_open_tickets_by_category`, `update_ticket_category_field_definitions` need facade-level tests
- `bot/core/db/ticket_db.py` — `get_stale_tickets`, `get_open_ticket_channel_ids`, `update_ticket_last_activity` need facade-level tests
- `bot/core/db/greeting_db.py` — `upsert_greeting_config` needs facade-level test
- `bot/core/db/infraction_db.py` — `deactivate_infraction` needs facade-level test
- `bot/cogs/sentinel.py` — `warn` happy path (behavior, not i18n), `_validate_target` denial paths, escalation paths
- `bot/cogs/core.py` — `_build_cog_help_embed`, `_build_help_pages`, `_resolve_prefix`
- `bot/utils/brand.py` — PRIMARY/ACCENT unused; need contract test or removal decision
- `docs/MANUAL.md` — Dynamic hybrid command discovery test (verify all registered commands appear)

### Approaches

#### 1. Models at 0% coverage (economy_config, member)

**Approach**: Pure unit tests for `from_db_row`/`to_db_dict` round-trips, defaults, datetime handling.

- **Pros**: No mocking needed, fast, high confidence
- **Cons**: Low complexity, minimal risk
- **Effort**: Low (1-2 test files, ~50-80 lines each)

**Test plan**:
- `test_economy_config_model.py` — `from_db_row` with all fields, defaults, `to_db_dict` round-trip, missing keys
- `test_member_model.py` — `from_db_row` with datetime fields, `to_db_dict` isoformat serialization, defaults, round-trip

#### 2. bot/__main__.py

**Approach**: Test `main()` function with mocked dependencies.

- **Pros**: Proves entry point bootstraps correctly
- **Cons**: Heavy mocking required (BotConfig, NebulosaBot, discord.Intents, asyncio.run)
- **Effort**: Low-Medium (~40 lines)

**Decision**: This module is thin glue code. Testing it adds little value beyond proving imports work. **Recommend: test import + main() call with mocks, or mark as dead code if `app.py` is the real entry point.**

#### 3. DB facade coverage (ticket_category_db, ticket_db, greeting_db, infraction_db)

**Approach**: Add facade-level tests using the existing `FakeSupabaseClient` pattern from `test_database.py`.

- **Pros**: Reuses proven test infrastructure, covers real query chains
- **Cons**: Need to replicate FakeSupabaseClient pattern per mixin
- **Effort**: Medium (4 test files, ~100-150 lines each)

**Test plan**:
- `test_ticket_category_db.py` — `count_open_tickets_by_category` (count="exact" response), `update_ticket_category_field_definitions` (guild-scoped update)
- `test_ticket_db.py` — `get_stale_tickets` (time-based filter), `get_open_ticket_channel_ids` (channel ID extraction), `update_ticket_last_activity` (channel-scoped update)
- `test_greeting_db.py` — `upsert_greeting_config` (upsert + _on_write callback)
- `test_infraction_db.py` — `deactivate_infraction` (soft-delete), `get_infractions` with type/after filters

#### 4. Sentinel behavior tests

**Approach**: Add behavioral tests for warn/mute/kick happy paths and deny scenarios, separate from i18n tests.

- **Pros**: Proves moderation logic works regardless of locale
- **Cons**: Some overlap with existing `test_sentinel_cog.py` (which tests i18n)
- **Effort**: Medium (~200-300 lines)

**Test plan**:
- `test_sentinel_behavior.py`:
  - `test_warn_persists_infraction` — infraction_service.warn() called, log sent
  - `test_warn_auto_escalation_mute` — escalation triggers mute
  - `test_warn_auto_escalation_kick` — escalation triggers kick
  - `test_mute_applies_timeout` — member.timeout() called with correct duration
  - `test_kick_confirmation_dialog` — ephemeral ConfirmCancelView sent
  - `test_ban_confirmation_dialog` — ephemeral ConfirmCancelView sent
  - `test_validate_target_deny_self` — self-target returns False
  - `test_validate_target_deny_hierarchy` — higher role returns False
  - `test_validate_target_deny_bot_target` — targeting bot returns False

#### 5. Core help builder

**Approach**: Test `_build_cog_help_embed` and `_build_help_pages` as pure functions.

- **Pros**: Help builder is a pure function, easy to test
- **Cons**: Needs mock bot with cogs/commands
- **Effort**: Low (~80-100 lines)

**Test plan**:
- `test_core_help_builder.py`:
  - `test_build_cog_help_embed_returns_embed` — with visible commands
  - `test_build_cog_help_embed_returns_none_for_empty_cog` — no commands
  - `test_build_cog_help_embed_returns_none_for_missing_cog` — cog not found
  - `test_build_help_pages_one_page_per_cog` — multiple cogs
  - `test_resolve_prefix_from_config` — guild_config present
  - `test_resolve_prefix_fallback` — no guild_config

#### 6. Brand PRIMARY/ACCENT

**Approach**: Decision needed — these constants are defined but never imported.

- **Option A**: Remove PRIMARY/ACCENT as dead code (they're not used anywhere in `bot/`)
- **Option B**: Keep them and add contract tests proving they're importable + correct values
- **Option C**: Find where they SHOULD be used and wire them in

**Recommendation**: **Option B** — keep PRIMARY/ACCENT as brand tokens (they're part of the palette spec), add contract tests proving:
- All 6 tokens are importable
- Values are correct hex
- No production code uses hardcoded hex instead of brand tokens

#### 7. MANUAL dynamic hybrid command discovery

**Approach**: Add a test that discovers all `hybrid_command` decorators at runtime and verifies they appear in MANUAL.md.

- **Pros**: Prevents drift between code and docs
- **Cons**: Requires importing all cogs, which may need mocking
- **Effort**: Low-Medium (~60-80 lines)

**Test plan**:
- `test_manual_dynamic_discovery.py`:
  - Import all cog modules, discover `@commands.hybrid_command` decorated functions
  - Assert each command name appears in MANUAL.md
  - Assert each command has a description in the manual

### Recommendation

**Execute in this order** (cheapest wins first):

1. **Models** (economy_config, member) — pure dataclass tests, no mocking, ~30 min
2. **Brand contract tests** — prove all 6 tokens exist and are correct, ~15 min
3. **DB facade tests** (ticket_category_db, ticket_db, greeting_db, infraction_db) — reuse FakeSupabaseClient, ~1 hr
4. **Core help builder** — pure function tests, ~20 min
5. **Sentinel behavior tests** — warn/mute/kick happy path + deny, ~1 hr
6. **MANUAL dynamic discovery** — hybrid command inventory check, ~30 min
7. **bot/__main__.py** — thin glue, lowest priority; test if time permits

### Risks

- **Risk 1**: DB facade tests may require extending FakeSupabaseClient for `count="exact"` support (already partially done in `test_database.py`)
- **Risk 2**: Sentinel behavior tests may overlap with existing i18n tests — need clear separation
- **Risk 3**: Dynamic command discovery test may break if cog loading order changes — should be resilient to ordering
- **Risk 4**: PRIMARY/ACCENT removal could break future code that imports them — safer to keep and test

### Ready for Proposal

**Yes** — exploration is complete. The orchestrator can proceed to `sdd-propose` with:
- Clear scope: 7 work areas identified
- Effort estimates: ~3-4 hours total
- Dependencies: None (all areas are independent)
- Risk mitigation: FakeSupabaseClient reuse, clear test separation
