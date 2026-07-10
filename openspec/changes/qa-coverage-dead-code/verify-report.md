# Verification Report: QA Coverage & Dead Code Cleanup (Cycle 2)

**Change**: `qa-coverage-dead-code`
**Artifact store**: OpenSpec
**Mode**: Strict TDD (`strict_tdd: true`; runner: `uv run pytest`)
**Implementation reviewed**: `947f58c`, `3bd1d61`, `ebd0081` on `master`
**Status input**: `gentle-ai sdd-status qa-coverage-dead-code --json --instructions` reported full artifacts, 24/24 tasks complete, `verify` ready, and no blocked reasons.

## Verdict: FAIL

All runtime, lint, type, build, and coverage commands pass. However, five REQUIRED spec scenarios have no passing covering test and/or expose an API contract that the current implementation cannot satisfy. Strict TDD verification therefore blocks archive readiness.

---

## Artifact and Task Completeness

| Artifact | Result | Evidence |
|---|---|---|
| Proposal | ✅ Present | `proposal.md` |
| Delta specs | ✅ Present | 6 capability specs |
| Design | ✅ Present | `design.md` |
| Tasks | ✅ Complete | 24/24 checked; no unchecked implementation task |
| Apply progress | ⚠️ Present, incomplete/inaccurate traceability | `apply-progress.md`; see TDD section |
| Verify report | ✅ Written | This file |

## Runtime and Quality Evidence

| Command | Result | Evidence |
|---|---|---|
| `uv run pytest` | ✅ PASS | 1331 passed, 3 skipped; 87.39% coverage |
| `uv run pytest -W error` | ✅ PASS | 1331 passed, 3 skipped; no warnings promoted to failures |
| Relevant TDD test groups (`--no-cov`) | ✅ PASS | 50 passed: member, facade, infraction-service/cog, and Sentinel behavior groups |
| `uv run pytest --cov=bot --cov-report=term-missing` | ✅ PASS | 87.39%, above configured 75% threshold |
| `uv run ruff check bot/` | ✅ PASS | No issues in 65 source files |
| `uv run mypy bot` | ✅ PASS | No errors |
| `uv run python -m py_compile bot/__main__.py` | ✅ PASS | Exit 0 |
| `git diff --check d14ee24..HEAD` | ✅ PASS | No whitespace errors in this change |

## Behavioral Compliance Matrix

### Brand tokens

| Scenario | Passing runtime evidence | Status |
|---|---|---|
| All six tokens are importable | `tests/test_brand.py` import tests | ✅ PASS |
| Token values match palette | `tests/test_brand.py` asserts all six values | ✅ PASS |
| No hardcoded production embed hex colors | `TestNoHardcodedHexColors`; source scan finds `0x...` only in `bot/utils/brand.py` | ✅ PASS |

### Manual discovery

| Scenario | Passing runtime evidence | Status |
|---|---|---|
| All hybrid commands appear in the manual | `test_dynamic_discovery_all_hybrid_commands_in_manual` | ✅ PASS |
| Each command has a non-empty description | The dynamic test asserts only `/{command}` presence; no test inspects a following description | ❌ UNTESTED — CRITICAL |
| Discovery is resilient to arbitrary cog import order | The implementation returns a sorted set, but the test runs one import order only; no permutation/order-independence test exists | ❌ UNTESTED — CRITICAL |

### Database facades

| Scenario | Passing runtime evidence | Status |
|---|---|---|
| Category count returns exact count | `TestCountOpenTicketsByCategory.test_returns_exact_count`; `guildId`, category, status, and `count="exact"` are separately asserted | ✅ PASS |
| Field-definition update is called as `(guild_id, category_id, fields)` and scoped | Test passes only with `(category_id, guild_id, fields)`; production signature is `update_ticket_category_field_definitions(category_id, guild_id, fields)` | ❌ FAIL — CRITICAL API contract mismatch |
| Stale tickets use guild, status, and cutoff filters | `tests/test_ticket_db.py::TestGetStaleTickets` | ✅ PASS |
| Open ticket channel IDs are extracted | `TestGetOpenTicketChannelIds.test_returns_channel_ids` | ✅ PASS (uses 3 distinct IDs rather than the scenario's 4) |
| Last activity update accepts `(guild_id, channel_id, timestamp)` and targets that guild/channel | Production and tests accept only `channel_id`; timestamp is generated internally and the update has no `guildId` filter | ❌ FAIL — CRITICAL API and guild-scope mismatch |
| Greeting upsert accepts `(guild_id, config)`, persists, and fires `_on_write` | Production and test use only `upsert_greeting_config(config)` | ❌ FAIL — CRITICAL API contract mismatch |
| Infraction deactivation sets `active=false` | `tests/test_infraction_db.py`; payload and both `guildId`/`id` filters asserted | ✅ PASS |

### Help builders

| Scenario | Passing runtime evidence | Status |
|---|---|---|
| Visible cog commands render in an embed | `TestBuildCogHelpEmbed.test_returns_embed_for_visible_commands` | ✅ PASS |
| Empty cog returns `None` | `test_returns_none_for_empty_cog` | ✅ PASS |
| Missing cog returns `None` | `test_returns_none_for_missing_cog` | ✅ PASS |
| One page per non-empty cog | `TestBuildHelpPages.test_multiple_cogs_produce_multiple_pages` | ✅ PASS |
| Prefix comes from guild config | `TestResolvePrefix.test_prefix_from_guild_config` | ✅ PASS |
| Prefix falls back to default | Both no-guild and no-config fallback tests | ✅ PASS |

### Models

| Scenario | Passing runtime evidence | Status |
|---|---|---|
| EconomyConfig maps complete DB rows | `tests/test_economy_config_model.py` | ✅ PASS |
| EconomyConfig round-trips to DB dict | `test_to_db_dict_round_trip` | ✅ PASS |
| EconomyConfig defaults missing values | `test_from_db_row_defaults_for_missing_keys` | ✅ PASS |
| Member parses ISO datetime strings | `tests/test_member_model.py::test_from_db_row_all_fields` | ✅ PASS |
| Member serializes datetimes to ISO strings | `test_to_db_dict_with_datetime_instances` and round-trip test | ✅ PASS |
| Member defaults optional fields | `test_from_db_row_defaults_for_missing_keys` | ✅ PASS |

### Sentinel moderation

| Scenario | Passing runtime evidence | Status |
|---|---|---|
| Warn persists an infraction and sends a moderation log | `tests/test_sentinel_cog.py::TestWarnCommand` | ✅ PASS |
| Warn auto-escalates to mute | `tests/test_sentinel_behavior.py::test_warn_auto_mute_triggered_at_threshold` | ✅ PASS |
| Mute applies parsed timeout duration and logs | `TestMuteCommand.test_mute_adds_timeout_and_logs` | ✅ PASS |
| Kick sends an ephemeral confirmation view | `TestKickCommand.test_kick_shows_confirmation_before_executing` | ✅ PASS |
| Ban sends an ephemeral confirmation view | `TestBanCommand.test_ban_shows_confirmation_before_executing` | ✅ PASS |
| Self target is denied | `TestValidateTargetBotDenial.test_deny_self_target` | ✅ PASS |
| Higher-role target is denied | `TestValidateTargetBotDenial.test_deny_higher_role_target` | ✅ PASS |
| Bot target is denied | `TestValidateTargetBotDenial.test_deny_bot_as_target` | ✅ PASS |

**Scenario result**: 28 PASS, 5 CRITICAL failures/untested scenarios.

## Production Correctness

| Area | Result | Evidence |
|---|---|---|
| `Member.from_db_row` datetime handling | ✅ Correct | `_parse_dt()` converts ISO strings, preserves `None` and existing `datetime` instances; all 7 model tests pass; 100% file coverage. |
| `count_open_tickets_by_category` guild scope | ✅ Correct | Signature requires `guild_id`; query filters `guildId`, `categoryId`, and status; the only production caller passes `gid`. |
| `deactivate_infraction` guild scope | ✅ Correct | Signature requires `guild_id`; query filters `guildId` and `id`; the only production caller (`InfractionService.unwarn`) forwards `guild_id`. |
| `update_ticket_last_activity` scope | ❌ Incorrect for this delta | The required guild/timestamp contract was not implemented. `ticket_db.py` and `TicketsCog.on_message` remain channel-only. This also conflicts with the design and the Architecture rule requiring `guild_id` filtering in multi-guild queries. |
| Field-definition update contract | ❌ Incorrect for this delta | Query filters are correct, but its positional interface reverses the spec's required guild/category order. |
| Greeting upsert contract | ❌ Incorrect for this delta | The established config-only API conflicts with the delta's required `(guild_id, config)` call. |

## Design Coherence

| Design decision | Result | Notes |
|---|---|---|
| Minimal Member datetime correction | ✅ Aligned | Implemented exactly as designed and covered by runtime tests. |
| Guild-scoped category count and infraction deactivation | ✅ Aligned | Implemented with call-site updates and façade tests. |
| Last-activity façade contract | ❌ Diverged | Design lines 37 and 50 require `update_ticket_last_activity(guild_id, channel_id, timestamp)`; implementation was not changed. |
| Three reviewable PR slices | ✅ Aligned | The three implementation commits are present on `master`. |
| Apply report says “None” deviations | ⚠️ Inaccurate | The last-activity contract divergence must be recorded. |

## TDD Compliance

| Check | Result | Details |
|---|---|---|
| TDD evidence reported | ✅ | `apply-progress.md` contains a TDD Cycle Evidence table. |
| Task-to-evidence traceability | ⚠️ | 13 evidence rows for 24 completed tasks. PR1 tasks 1.1–5.1 and several PR2 call-site/update tasks have no standalone row. |
| RED confirmed | ⚠️ | Referenced test files exist, but task 7.2 records `N/A` rather than a RED test and the absent task rows cannot be independently checked. |
| GREEN confirmed | ✅ | Full suite passed twice (including `-W error`); the listed focused groups passed 50/50 directly. |
| Triangulation | ✅ | Models and façade tests exercise success, empty/default, filter, and disconnected paths; Sentinel covers escalation plus three denial modes. |
| Safety net | ✅ | `N/A (new)` entries correspond to new test files; modified-file entries record a baseline suite. |

The progress summary is also numerically misleading: it calls 37 tests the all-PR total, while the implementation diff adds 60 test definitions and removes/renames one (net +59), matching the proposal baseline of 1272 and current 1331 passing tests. The reported `1294 + 37 = 1331` is only valid when 1294 is treated as the post-PR1 baseline.

### Test Layer Distribution

| Layer | Added test definitions | Files | Tools |
|---|---:|---:|---|
| Unit | 26 | 5 | pytest + pytest-asyncio/mocks |
| Facade | 33 | 5 | pytest + `FakeSupabaseClient` |
| Integration | 1 | 1 | pytest; runtime cog-module/manual discovery |
| E2E | 0 | 0 | Not available |
| **Total** | **60** | **11** | **1 renamed/removed test; net +59** |

### Changed Production File Coverage

Coverage is whole-file coverage from the required `--cov=bot` run; test files are excluded by that source setting. Changed hunks for the Member and the two repaired guild-scoped facades execute, but pre-existing lines reduce two file totals.

| File | Line coverage | Uncovered lines | Rating |
|---|---:|---|---|
| `bot/models/member.py` | 100% | — | ✅ Excellent |
| `bot/core/db/ticket_category_db.py` | 49% | 33-49, 53-65, 69-75, 79-83 | ⚠️ Low |
| `bot/core/db/infraction_db.py` | 71% | 36-53, 85, 87, 100 | ⚠️ Low |
| `bot/cogs/tickets.py` | 81% | Pre-existing uncovered branches; changed line 283 is covered | ⚠️ Acceptable |
| `bot/services/infraction_service.py` | 100% | — | ✅ Excellent |

**Average changed-file coverage**: 80.2%. The two low whole-file values are non-blocking coverage warnings because the changed hunks execute and the configured aggregate threshold passes.

### Assertion Quality

**Assertion quality**: ✅ All reviewed changed assertions invoke production behavior and verify values, query filters, state transitions, or observable Discord interactions. No tautologies, ghost loops, assertion-free calls, or smoke-only tests were found.

## Issues

### CRITICAL

1. **Manual descriptions are untested.** `specs/docs-manual/spec.md` requires every dynamically discovered hybrid command to have a non-empty following description. `tests/test_manual.py` checks only command-name presence.
2. **Manual discovery order resilience is untested.** Sorting a result from one run is not a test of arbitrary cog import order; no reordered-import test exists.
3. **`update_ticket_category_field_definitions` violates the specified positional API.** The spec requires `(guild_id, category_id, fields)`; production and its test use `(category_id, guild_id, fields)`.
4. **`update_ticket_last_activity` violates the specified and designed guild/timestamp contract.** It remains `(channel_id)` only and lacks a `guildId` filter. This conflicts with `qa-db-facade-coverage/spec.md`, `design.md`, and `AGENTS.md` Architecture: “Always filter by `guild_id` in multi-guild queries.”
5. **`upsert_greeting_config` violates the specified API.** The spec requires `(guild_id, config)` while production and test use the established config-only API. Resolve the spec/API discrepancy and add a passing contract test.

### WARNING

1. Strict-TDD traceability is incomplete: 13 evidence rows cover 24 completed tasks, and the summary misstates the test delta. Runtime results are valid, but the historical RED/GREEN evidence is not fully auditable.
2. `ticket_category_db.py` (49%) and `infraction_db.py` (71%) are below the Strict-TDD whole-file 80% coverage advisory, although their changed hunks are covered.
3. The open-channel-ID test demonstrates extraction with three IDs, not the scenario's stated four. It covers the generic behavior but should match the specified fixture size for exact traceability.
4. The proposal's rollback statement says the change has zero production modifications, but PR2 modifies five production files. The proposal otherwise acknowledges minimal contract corrections; reconcile the contradictory wording.

### SUGGESTION

1. Add explicit `assert_awaited_once_with(...)` assertions at the Sentinel cog boundary for warn parameters, not only downstream service effects.

## Archive Readiness

**Blocked.** Tasks are complete and runtime gates are green, but archive requires a clearly passing verification report with no CRITICAL issue. Correct or explicitly reconcile the five critical spec-contract/test gaps, then re-run Strict-TDD verification.
