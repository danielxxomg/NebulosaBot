# Proposal: QA Coverage & Dead Code Cleanup (Cycle 2)

## Intent

Close coverage gaps left by cycle 1 and add behavioral tests for untested code paths. Current baseline: 1272 tests, 0 warnings, ruff/mypy clean. Several modules sit at 0% or partial coverage (models, DB facades, sentinel behavior, help builder). This cycle adds contract and behavioral tests **plus minimal production fixes** where live code violates the intended contracts discovered in design (e.g. `Member.from_db_row` datetime parsing, DB facade guild/timestamp scope gaps).

## Scope

### In Scope
- Model unit tests: `economy_config`, `member` (from_db_row/to_db_dict round-trips)
- DB facade tests: `ticket_category_db`, `ticket_db`, `greeting_db`, `infraction_db`
- Sentinel behavior tests: warn/mute/kick happy paths + validate_target denials
- Core help builder tests: `_build_cog_help_embed`, `_build_help_pages`, `_resolve_prefix`
- Brand contract tests: prove PRIMARY/ACCENT + 4 other tokens are importable with correct hex values
- MANUAL dynamic discovery test: verify all hybrid commands appear in MANUAL.md with required headings

### Out of Scope
- `bot/__main__.py` (thin glue, 0% — not worth testing)
- `ticket_service` split or refactoring
- mypy wildcard strictness improvements
- Product features or dashboard changes
- Deleting PRIMARY/ACCENT (keeping as brand SSOT)
- Large refactors (ticket_service split, mypy wildcards) — later cycles
- Non-minimal production rewrites beyond contract corrections for models/DB facades

## Capabilities

### New Capabilities
- `qa-model-coverage`: Unit tests for economy_config and member dataclasses (from_db_row, to_db_dict, defaults, datetime handling)
- `qa-db-facade-coverage`: Facade-level tests for ticket_category_db, ticket_db, greeting_db, infraction_db using FakeSupabaseClient
- `qa-sentinel-behavior`: Behavioral tests for warn/mute/kick happy paths and validate_target deny scenarios (separate from i18n tests)
- `qa-help-builder`: Unit tests for _build_cog_help_embed, _build_help_pages, _resolve_prefix

### Modified Capabilities
- `brand-tokens`: Add contract tests proving all 6 tokens are importable with correct hex values and no hardcoded hex in production code
- `docs-manual`: Add dynamic hybrid command discovery test verifying all registered commands appear in MANUAL.md

## Approach

Work cheapest-first, each area independent:

1. **Models** — pure dataclass tests, no mocking (~50-80 lines each)
2. **Brand contract** — import + hex value assertions (~30 lines)
3. **DB facades** — reuse `FakeSupabaseClient` from `test_database.py` (~100-150 lines each)
4. **Core help builder** — mock bot with cogs/commands (~80-100 lines)
5. **Sentinel behavior** — mock Interaction/Member, test infraction_service calls (~200-300 lines)
6. **MANUAL discovery** — import cogs, discover @hybrid_command decorators, assert presence in MANUAL.md (~60-80 lines)

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `tests/test_economy_config_model.py` | New | Round-trip + defaults for economy_config |
| `tests/test_member_model.py` | New | Round-trip + datetime for member |
| `tests/test_ticket_category_db.py` | New | count_open_tickets_by_category, update_field_definitions |
| `tests/test_ticket_db.py` | New | get_stale_tickets, get_open_ticket_channel_ids, update_last_activity |
| `tests/test_greeting_db.py` | New | upsert_greeting_config |
| `tests/test_infraction_db.py` | New | deactivate_infraction |
| `tests/test_sentinel_behavior.py` | New | warn/mute/kick happy path + validate_target denials |
| `tests/test_core_help_builder.py` | New | help embed builder + resolve_prefix |
| `tests/test_brand_contract.py` | New | 6 tokens importable, correct hex |
| `tests/test_manual_dynamic_discovery.py` | New | hybrid command inventory check |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| FakeSupabaseClient needs `count="exact"` support | Med | Already partially done in test_database.py; extend as needed |
| Sentinel behavior tests overlap with i18n tests | Med | Separate file (test_sentinel_behavior.py), focus on service calls not locale |
| Dynamic command discovery fragile to cog load order | Low | Sort discovered commands alphabetically before comparison |

## Rollback Plan

All changes are new test files — zero production code modified. Delete any test file to revert that area. No migrations, no config changes.

## Dependencies

- Existing `FakeSupabaseClient` pattern in `tests/test_database.py`
- Existing `test_sentinel_cog.py` for reference on mocking patterns

## Success Criteria

- [ ] `economy_config` and `member` models reach 100% coverage
- [ ] Targeted DB facade methods (6 methods across 4 mixins) covered
- [ ] Sentinel behavior tests pass independent of i18n tests
- [ ] Brand contract test proves all 6 tokens correct
- [ ] MANUAL dynamic discovery test passes
- [ ] Overall coverage increases (baseline: 74.59%)
- [ ] `uv run pytest` green with `-W error`

## Proposal Question Round

This proposal was generated from locked orchestrator decisions (auto mode). Assumptions:
1. PRIMARY/ACCENT are kept as brand SSOT with contract tests — no removal
2. `bot/__main__.py` is excluded (thin glue, not worth testing)
3. DB facade tests target only the 6 specific untested methods identified in exploration
4. Sentinel behavior tests go in a separate file from i18n tests
5. No production code changes — test-only cycle
