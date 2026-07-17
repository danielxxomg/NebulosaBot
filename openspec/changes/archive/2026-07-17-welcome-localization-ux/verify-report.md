```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:0db8faca9dad49e916720529ea2780cc72e70bbd5ac9d08a29aa91cc581601de
verdict: pass
blockers: 0
critical_findings: 0
requirements: 12/12
scenarios: 38/38
test_command: uv run pytest -v
test_exit_code: 0
test_output_hash: sha256:07d6f910da011215b6248f0c15e00ed586a6ffae49c489cd2c43fd9583e39f40
build_command: npm run build
build_exit_code: 0
build_output_hash: sha256:55e32f544ea8433b190b5c01edd43d9e65a5b6ea2b73ee4e887f8ee6a1652459
```

## Verification Report

**Change**: `welcome-localization-ux`  
**Version**: N/A  
**Mode**: Strict TDD

### Native preflight

The structured native status was read before artifact judgment. It identified the
OpenSpec change, all required context files, and 21/21 completed tasks. The
status projection reported `nextRecommended: resolve-review` because review
artifacts were not projected into the OpenSpec path set. The authoritative
post-apply validation was then run for lineage `review-18997557214fd367` in this
checkout and returned `allow` with generation 1 and evidence hash
`sha256:1ab922ddcda2182c0f9a85fc8f84462e9e0fb4849d63cda67844f223057620dc`.

### Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 21 |
| Tasks complete | 21 |
| Tasks incomplete | 0 |
| Proposal/specs/design/tasks/apply-progress | All present and read |

### Build & Tests Execution

All commands below ran in the temporary checkout only. Dashboard commands ran
with `dashboard/` as the working directory.

| Command | Exit | Output hash | Result |
|---------|------|-------------|--------|
| `uv run pytest -v` | 0 | `sha256:07d6f910da011215b6248f0c15e00ed586a6ffae49c489cd2c43fd9583e39f40` | 1,559 passed, 3 skipped, coverage 88.31% |
| `uv run pytest --no-cov tests/test_greeting_config.py tests/test_greeting_db.py tests/test_i18n.py tests/test_greeting_service.py tests/test_guild_service.py tests/test_image_service.py tests/test_greetings_cog.py tests/test_realtime.py -v` | 0 | `sha256:89f86b208d7110fa86fdbf4ffd388398231e79003c7d92c2e55b725274240662` | 246 passed |
| `npm test` | 0 | `sha256:c4dfbb1edb532a6415f71e5856a937415cd7473236d2645c68a760a82e553698` | 17 files, 240 passed |
| `npm test -- __tests__/lib/actions/greeting-actions.test.ts __tests__/app/greeting-page.test.tsx` | 0 | `sha256:a7025b13c18ff8582be7a6062f498226bddb786cd64a2ddd3427fcc606441d41` | 2 files, 23 passed |
| `npx tsc --noEmit` | 0 | `sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | Passed with empty output |
| `npm run build` | 0 | `sha256:55e32f544ea8433b190b5c01edd43d9e65a5b6ea2b73ee4e887f8ee6a1652459` | Next.js build, lint/type validation, and routes generated |

The clean checkout initially lacked the development Python environment, so the
required runner first returned exit 2 (`pytest` executable missing). The
non-source setup command `uv sync --extra dev --frozen` completed successfully;
the exact required `uv run pytest -v` command then passed as recorded above.

### Spec Compliance Matrix

#### `greeting-config` — 5 requirements, 14 scenarios

| Requirement | Scenario | Covering runtime test | Result |
|-------------|----------|------------------------|--------|
| GC-1 Onboarding channel column | New guild defaults to null | `tests/test_greeting_config.py::TestGreetingConfigDefaults::test_default_guild_id_only` | ✅ COMPLIANT |
| GC-1 | Existing rows remain valid after additive migration | `tests/test_greeting_config.py::TestFromDbRow::test_minimal_row_uses_defaults` | ✅ COMPLIANT |
| GC-1 | Set onboarding channel | `tests/test_greeting_db.py::TestUpsertGreetingConfig::test_persists_onboarding_channel` | ✅ COMPLIANT |
| GC-1 | Clear onboarding channel | `tests/test_greeting_db.py::TestUpsertGreetingConfig::test_clears_onboarding_channel_to_null` | ✅ COMPLIANT |
| GC-2 Onboarding cache/Realtime invalidation | Cache invalidated on onboarding update | `tests/test_greeting_service.py::TestSaveConfig::test_save_config_upserts_and_invalidates` | ✅ COMPLIANT |
| GC-2 | Realtime CDC invalidates onboarding channel | `tests/test_realtime.py::TestCdcDispatch::test_greeting_config_onboarding_update_invalidates_cached_config` | ✅ COMPLIANT |
| GC-2 | Dashboard write uses Realtime only | `dashboard/__tests__/lib/actions/greeting-actions.test.ts` onboarding persistence test | ✅ COMPLIANT |
| GC-3 Greeting columns | New guild defaults | `tests/test_greeting_config.py::TestGreetingConfigDefaults::test_default_guild_id_only` | ✅ COMPLIANT |
| GC-3 | Onboarding channel round-trips | `tests/test_greeting_config.py::TestRoundtrip::test_roundtrip_preserves_all_fields` | ✅ COMPLIANT |
| GC-4 CRUD via services | Update welcome channel | `tests/test_greetings_cog.py::TestWelcomeConfigCommand::test_channel_saves_new_channel` | ✅ COMPLIANT |
| GC-4 | Disable welcome card | `tests/test_greeting_service.py::TestDispatchWelcome::test_card_disabled_with_message_sends_text_only` | ✅ COMPLIANT |
| GC-4 | Update onboarding channel via service | `tests/test_guild_service.py::test_greeting_config_delegates_to_greeting_service` | ✅ COMPLIANT |
| GC-5 Cache-first reads | Cache invalidation on update | `tests/test_greeting_service.py::TestSaveConfig::test_save_config_upserts_and_invalidates` | ✅ COMPLIANT |
| GC-5 | Cache hit returns onboarding value without DB | `tests/test_greeting_service.py::TestGetConfig::test_cache_hit_preserves_onboarding_channel` | ✅ COMPLIANT |

#### `i18n-system` — 1 requirement, 6 scenarios

| Requirement | Scenario | Covering runtime test | Result |
|-------------|----------|------------------------|--------|
| I18N-1 Greeting card/CTA keys | Spanish card keys resolve | `tests/test_i18n.py::test_greeting_keys_interpolate_without_unresolved_tokens[111-…]` | ✅ COMPLIANT |
| I18N-1 | English card keys resolve | `tests/test_i18n.py::test_greeting_keys_interpolate_without_unresolved_tokens[222-…]` | ✅ COMPLIANT |
| I18N-1 | Member count interpolation | Same parametrized test, `{count}` → `7` | ✅ COMPLIANT |
| I18N-1 | CTA channel interpolation | Same parametrized test, `{channel}` → `<#123>` | ✅ COMPLIANT |
| I18N-1 | Greeting/message placeholder namespaces stay distinct | `tests/test_i18n.py::test_greeting_fallback_precedes_raw_key_and_preserves_template_namespace` | ✅ COMPLIANT |
| I18N-1 | Spanish fallback precedes raw key | Same fallback test | ✅ COMPLIANT |

#### `welcome-goodbye` — 6 requirements, 18 scenarios

| Requirement | Scenario | Covering runtime test | Result |
|-------------|----------|------------------------|--------|
| WG-1 Localized card text | Spanish welcome card | `tests/test_greeting_service.py::TestDispatchWelcome::test_spanish_live_welcome_dispatch_passes_localized_copy_and_cta` | ✅ COMPLIANT |
| WG-1 | English goodbye card | `tests/test_greeting_service.py::TestDispatchGoodbye::test_localized_goodbye_dispatch_hands_off_copy_without_cta[en-…]` | ✅ COMPLIANT |
| WG-1 | Caller passes translated strings | `tests/test_image_service.py::TestGenerateGreetingCard::test_supplied_localized_strings_are_rendered` | ✅ COMPLIANT |
| WG-1 | Test commands use localized strings | `tests/test_greetings_cog.py::TestWelcomeTestCommand::test_welcome_test_passes_localized_copy_and_guild_icon` | ✅ COMPLIANT |
| WG-2 Branded identity treatment | Guild icon present | `tests/test_image_service.py::TestGenerateGreetingCard::test_greeting_card_renders_guild_identity_and_premium_hierarchy` | ✅ COMPLIANT |
| WG-2 | Missing guild icon fallback | `tests/test_image_service.py::TestGenerateGreetingCard::test_missing_assets_use_deterministic_placeholders` | ✅ COMPLIANT |
| WG-2 | Avatar fetch failure fallback | `tests/test_image_service.py::TestGenerateGreetingCard::test_avatar_fetch_failure_keeps_localized_copy` | ✅ COMPLIANT |
| WG-3 Welcome CTA | Default welcome with CTA | `tests/test_greeting_service.py::TestDispatchWelcome::test_resolvable_onboarding_channel_appends_localized_cta` | ✅ COMPLIANT |
| WG-3 | Custom message preserves CTA | `tests/test_greeting_service.py::TestDispatchWelcome::test_custom_welcome_message_preserves_onboarding_cta` | ✅ COMPLIANT |
| WG-3 | No onboarding channel omits CTA safely | `tests/test_greeting_service.py::TestDispatchWelcome::test_missing_or_unresolvable_onboarding_channel_omits_cta[None]` | ✅ COMPLIANT |
| WG-3 | Inaccessible onboarding channel omits CTA safely | Same parametrized test, inaccessible target case | ✅ COMPLIANT |
| WG-3 | Goodbye has no CTA | `tests/test_greeting_service.py::TestDispatchGoodbye::test_goodbye_never_appends_welcome_cta` | ✅ COMPLIANT |
| WG-4 Card generation | Welcome card receives localized identity inputs | `tests/test_image_service.py::TestGenerateGreetingCard::test_supplied_localized_strings_are_rendered` | ✅ COMPLIANT |
| WG-4 | Missing avatar still renders localized card | `tests/test_image_service.py::TestGenerateGreetingCard::test_handle_missing_avatar_none` | ✅ COMPLIANT |
| WG-4 | Missing guild icon still renders localized card | `tests/test_image_service.py::TestGenerateGreetingCard::test_missing_assets_use_deterministic_placeholders` | ✅ COMPLIANT |
| WG-5 Welcome card on join | Enabled join sends card and CTA content | `tests/test_greeting_service.py::TestDispatchWelcome::test_card_enabled_sends_welcome_card` plus CTA cases | ✅ COMPLIANT |
| WG-5 | Disabled welcome card sends no card | `tests/test_greeting_service.py::TestDispatchWelcome::test_disabled_skips_before_card_toggle` | ✅ COMPLIANT |
| WG-6 Goodbye card on leave | Enabled leave sends localized card | `tests/test_greeting_service.py::TestDispatchGoodbye::test_localized_goodbye_dispatch_hands_off_copy_without_cta` | ✅ COMPLIANT |

**Compliance summary**: 38/38 scenarios have passing runtime coverage. The
approved product boundary is preserved: one welcome message, optional separate
onboarding destination, card-enabled welcome sends card plus CTA, an empty
card-disabled welcome is silent, and goodbye never receives a CTA.

### Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| Optional onboarding persistence | ✅ Implemented | Nullable additive migration, model mapping, DB upsert/read, and null clearing are present. |
| Cache-first greeting CRUD | ✅ Implemented | GreetingService owns cache-first reads and invalidates after writes; GuildService delegates. |
| Realtime invalidation | ✅ Implemented | Existing generic `greeting_config` CDC path invalidates the guild cache; onboarding UPDATE is covered. |
| Dashboard persistence | ✅ Implemented | Server Action validates, upserts, revalidates, and does not call a bot webhook. |
| ES/EN greeting namespace | ✅ Implemented | Both locale files define card and CTA keys; fallback/interpolation remain in `t()`. |
| Caller-side localization | ✅ Implemented | GreetingService/Cog resolve translated strings before the Pillow renderer. |
| Branded renderer | ✅ Implemented | Guild/member identity, gradient hierarchy, circular assets, and deterministic placeholders are present. |
| Welcome CTA composition | ✅ Implemented | Resolvable cached onboarding channels produce localized CTA content; inaccessible targets omit it safely. |
| Goodbye CTA exclusion | ✅ Implemented | Goodbye dispatch formats only goodbye text and never composes onboarding CTA. |
| Async renderer boundary | ✅ Implemented | Greeting card generation is synchronous Pillow work invoked through `asyncio.to_thread()`. |
| Existing behavior safety | ✅ Implemented | Card-disabled empty welcome remains silent and renderer compatibility fallback is bounded to unexpected keyword errors. |
| Migration compatibility | ✅ Implemented | `ADD COLUMN IF NOT EXISTS` preserves existing rows and keeps the field nullable. |

### Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| GreetingService owns orchestration and caller-side translation | ✅ Yes | Translation and CTA resolution occur before renderer invocation. |
| Pillow renderer remains pure and receives formatted strings | ✅ Yes | Renderer does not resolve guild language or query Discord. |
| CTA remains in message content, not the banner | ✅ Yes | Welcome content composition is separate from image generation. |
| Nullable onboarding field uses existing cache-first/Realtimes path | ✅ Yes | No duplicate persistence owner or dashboard webhook was introduced. |
| Asset/API fetches are avoided during dispatch | ✅ Yes | Guild cache resolution is used; fetch/decode failures become placeholders. |
| Dashboard exposes one optional onboarding control | ✅ Yes | The greeting page defaults null and submits the field with the existing form. |

### TDD Compliance

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | `apply-progress.md` contains cumulative TDD Cycle Evidence tables. |
| All tasks have tests | ✅ | 21/21 task rows have corresponding focused or suite-level runtime evidence. |
| RED confirmed (tests exist) | ✅ | All concrete test paths in the evidence exist; the final regression task is suite-level. |
| GREEN confirmed (tests pass) | ✅ | 246 changed-area Python tests and 23 changed-area dashboard tests pass. |
| Triangulation adequate | ✅ | Locale, service, renderer, dashboard, cache, null, inaccessible, and error paths vary expected outcomes. |
| Safety net for modified files | ✅ | Apply evidence records baselines for applicable PR1–PR3 files and corrections. |

**TDD Compliance**: 6/6 checks passed.

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit | 90 | 5 Python files | pytest |
| Integration | 156 Python + 23 dashboard | 3 Python + 2 dashboard files | pytest mocks, Vitest mocks |
| E2E | 0 | 0 | Unavailable by project configuration |
| **Total** | **269** | **10** | |

### Changed File Coverage

| File | Line % | Branch % | Uncovered Lines | Rating |
|------|--------|----------|-----------------|--------|
| `bot/cogs/greetings.py` | 93% | N/A | Not emitted by pytest-cov | ✅ Excellent |
| `bot/core/db/greeting_db.py` | 100% | N/A | — | ✅ Excellent |
| `bot/core/i18n.py` | 95% | N/A | Not emitted by pytest-cov | ✅ Excellent |
| `bot/core/realtime.py` | 89% | N/A | Not emitted by pytest-cov | ⚠️ Acceptable |
| `bot/models/greeting_config.py` | 100% | N/A | — | ✅ Excellent |
| `bot/services/greeting_service.py` | 89% | N/A | Not emitted by pytest-cov | ⚠️ Acceptable |
| `bot/services/guild_service.py` | 92% | N/A | Not emitted by pytest-cov | ✅ Excellent |
| `bot/services/image_service.py` | 94% | N/A | Not emitted by pytest-cov | ✅ Excellent |
| Dashboard changed files | N/A | N/A | Vitest coverage not configured | ➖ Not available |

**Average changed Python file coverage**: 92.6% (simple mean of the eight
changed Python production files above). Repository total: 88.31%; configured
threshold: 75%.

### Assertion Quality

✅ No tautologies, ghost loops, assertion-free production paths, smoke-test-only
tests, or meaningless type-only assertions were found in the change-specific
assertions. Mock interaction assertions are paired with observable payload,
content, cache, file, or error behavior.

### Quality Metrics

| Tool | Result | Evidence |
|------|--------|----------|
| Ruff | ✅ Passed | `uv run ruff check` on changed production Python files; output hash `sha256:82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18`. |
| mypy | ⚠️ Warnings | `uv run mypy bot` exited 1 with 27 errors; changed `bot/cogs/greetings.py` has Discord decorator/stub errors, while the remaining errors are in unrelated existing cogs. |
| Dashboard TypeScript | ✅ Passed | `npx tsc --noEmit` exited 0 with empty output. |
| Dashboard lint script | ⚠️ Incomplete | `npm run lint` exited 1 after the deprecated `next lint` command opened an interactive ESLint configuration prompt. `npm run build` independently completed lint/type validation successfully. |

### Issues Found

**CRITICAL**: None.

**WARNING**:

1. Standalone dashboard `npm run lint` is not non-interactively executable in
   this checkout; it stops at the deprecated Next.js ESLint setup prompt.
2. Whole-project mypy exits 1 with 27 errors, including decorator/stub errors
   in changed `bot/cogs/greetings.py`; the production build and Python tests
   still pass.
3. `git diff --check` reports trailing whitespace at
   `apply-progress.md:258`; this is an SDD artifact-only hygiene issue.
4. Verification used mocked Discord/Supabase/Realtime boundaries; no live
   Discord API, Supabase query, or migration application was executed in this
   checkout. The migration is statically additive and the supplied project
   context confirms migration `20260716164148` is already applied.

**SUGGESTION**:

1. Replace the interactive/deprecated dashboard lint script with an explicit
   ESLint CLI configuration in a future tooling pass.
2. Add a migration-runner test or schema-level CI check if future verification
   must exercise SQL application rather than the current additive SQL and
   model-compatibility tests.

### Verdict

**PASS WITH WARNINGS**

All 21 tasks, 12 requirements, and 38 scenarios are covered by the current
implementation and passing runtime tests. Warnings are limited to repository
tooling/type-check debt, artifact whitespace, and the explicitly unavailable
live integration boundaries; no critical verification blocker was found.
