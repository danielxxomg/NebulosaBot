# Apply Progress: welcome-localization-ux — Phase 3 / PR3

## Status

- Mode: Strict TDD
- Artifact store: OpenSpec
- Apply state: all_done; PR3 implementation complete
- Work unit: Unit 3 — Renderer, cog, Realtime, and dashboard (PR3)
- PR base: PR2 stacked slice
- Delivery strategy: `auto-chain`
- Chain strategy: `stacked-to-main`
- Boundary: PR1 contains tasks 1.1–1.5; PR2 contains tasks 2.1–2.7; PR3 implements only tasks 3.1–3.9
- Runtime boundary: Mocked Discord, Realtime, and dashboard service tests only; no live Discord/Supabase runtime was executed

## Completed Tasks

- [x] 1.1 RED: Added `tests/test_greeting_config.py` coverage for a null `onboardingChannelId` and camelCase serialization.
- [x] 1.2 GREEN: Added nullable `GreetingConfig.onboarding_channel_id` with database row mapping and serialization.
- [x] 1.3 RED: Added `tests/test_greeting_db.py` coverage for upsert/get round-trips and clearing the channel to null.
- [x] 1.4 GREEN: Updated greeting DB persistence typing/documentation so the generic CRUD payload includes the nullable onboarding field.
- [x] 1.5 Created additive migration `migrations/016_greeting_onboarding_channel.sql` with `ADD COLUMN IF NOT EXISTS "onboardingChannelId" TEXT`.

## TDD Cycle Evidence

| Task | Test file | Layer | RED — test-first evidence | GREEN — implementation evidence | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|
| 1.1 | `tests/test_greeting_config.py` | Unit | Wrote null-default and camelCase round-trip assertions before adding the model field; the missing field/serialization contract was exposed. | `uv run pytest --no-cov tests/test_greeting_config.py tests/test_greeting_db.py -v` — exit 0, **17 passed**. | Covered null defaults, partial rows, populated rows, and full round-trip serialization. | Kept the dataclass defaults and existing field ordering; focused suite remained green. |
| 1.2 | `tests/test_greeting_config.py` | Unit | The test-first model assertions failed against the pre-change model because `onboarding_channel_id` and `onboardingChannelId` were absent. | Same focused run — exit 0, **17 passed** after the nullable field and mappings were added. | Non-null and null values both round-trip through `from_db_row()`/`to_db_dict()`. | Preserved existing defaults and camelCase database contract without changing unrelated fields. |
| 1.3 | `tests/test_greeting_db.py` | Unit | Wrote upsert/get and clear-to-null persistence assertions before the DB payload contract was updated; the onboarding payload behavior was absent. | Same focused run — exit 0, **17 passed**. | Exercised configured-channel, cleared-null, returned-channel, and returned-null paths. | Kept the existing fake-client CRUD test structure and cache/write-hook behavior unchanged. |
| 1.4 | `tests/test_greeting_db.py` | Unit | The new DB tests established the expected onboarding payload before the typed CRUD contract was updated. | Same focused run — exit 0, **17 passed** after the DB mixin contract/documentation update. | Verified both non-null and null payload values through the existing generic upsert path. | Reused `GreetingConfig.to_db_dict()` rather than introducing a second query or serialization path. |
| 1.5 | `tests/test_greeting_config.py`, `tests/test_greeting_db.py` | Unit/structural migration | Persistence tests were established first; the migration was then added as the additive schema step needed to support the tested nullable field. | Same focused run — exit 0, **17 passed**, confirming the model/DB persistence contract remains green with the migration artifact present. | Existing-row compatibility is represented by missing-field defaults and explicit null round-trips. | Migration is repeat-safe and additive via `IF NOT EXISTS`; no destructive SQL or runtime behavior was introduced. |

### PR2 — Unit 2 TDD Cycle Evidence

| Task | Test file | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| 2.1 | `tests/test_i18n.py` | Unit | ✅ Baseline focused suite: 63/63 passed | ✅ Added ES/EN card and CTA lookup/interpolation tests first; the new production-key test failed before locale entries existed. | ✅ Final focused run: 76 passed after shipped locale keys were added. | ✅ Parametrized ES/EN outputs and verified `{count}`/`{channel}` produce concrete text without unresolved tokens. | ✅ Kept the existing synchronous `t()` API and nested dot-key resolution unchanged. |
| 2.2 | `tests/test_i18n.py` | Unit | ✅ Baseline focused suite: 63/63 passed | ✅ Added missing-EN fallback and placeholder-namespace assertions first; fallback/namespace behavior was exercised before implementation changes. | ✅ Final focused run: 76 passed. | ✅ Removed the English key, verified Spanish fallback, then formatted `{mention}`/`{server}` independently from greeting placeholders. | ✅ Reused the existing fallback chain; no duplicate placeholder resolver was introduced. |
| 2.3 | `bot/locales/en.json`, `bot/locales/es.json` | Unit/structural locale data | ✅ Baseline focused suite: 63/63 passed | ✅ Real-locale completeness test failed with missing `greetings.card.welcome_title` before the entries were added. | ✅ Final focused run: 76 passed; both JSON files parse successfully. | ➖ Structural locale entries have finite required keys; interpolation is covered by 2.1. | ✅ Preserved all unrelated pending locale edits and added only the greeting namespace. |
| 2.4 | `tests/test_greeting_service.py` | Unit/integration with mocked Discord | ✅ Baseline focused suite: 63/63 passed | ✅ Added onboarding CRUD, resolvable CTA, omission, goodbye, custom-message, and renderer-handoff tests first; resolvable/custom CTA tests failed before service changes. | ✅ Final focused run: 76 passed. | ✅ Covered cache hit, DB persistence, null target, inaccessible target, custom text, card-disabled path, and goodbye path. | ✅ Extracted channel resolution and welcome-content composition helpers; production remained async and cache-first. |
| 2.5 | `bot/services/greeting_service.py` | Unit/integration with mocked Discord | ✅ Baseline focused suite: 63/63 passed | ✅ Service tests were written before production changes and failed on missing CTA composition and translated renderer kwargs. | ✅ Final focused run: 76 passed; `asyncio.to_thread()` handoff remains green. | ✅ Tested welcome/goodbye, card enabled/disabled, custom/empty text, and accessible/inaccessible channels. | ✅ Localized copy is resolved caller-side with `t()`; CTA composition is isolated from message-template formatting. |
| 2.6 | `tests/test_guild_service.py` | Unit with mocked services | ✅ Baseline focused suite: 63/63 passed | ✅ Delegation test failed first because `GuildService` did not accept a `GreetingService` dependency. | ✅ Final focused run: 76 passed. | ✅ Covered successful read/write delegation and the missing-dependency safety failure. | ✅ Asserted the DB greeting methods are not called by the facade, proving no duplicate field ownership. |
| 2.7 | `bot/services/guild_service.py` | Unit with mocked services | ✅ Baseline focused suite: 63/63 passed | ✅ Implemented only after 2.6 RED; delegated read/write methods now satisfy the failing contract. | ✅ Final focused run: 76 passed. | ✅ Optional dependency preserves existing callers while injected instances delegate all greeting CRUD. | ✅ Added a bounded `RuntimeError` for unconfigured delegation rather than creating a second persistence owner. |

### PR2 Test Summary

- **Total tests written**: 13 new focused assertions/cases across the three assigned test files.
- **Total tests passing**: 76/76 focused tests.
- **Layers used**: Unit and mocked service/Discord integration; E2E unavailable by project configuration.
- **Approval tests**: None — this unit adds behavior and preserves existing focused coverage; no standalone refactor task.
- **Pure functions created**: 3 bounded helpers for welcome content/channel resolution and existing template composition remains pure.

## Work Unit Evidence

| Evidence | Exact result |
|---|---|
| Focused test command | `uv run pytest --no-cov tests/test_greeting_config.py tests/test_greeting_db.py -v` — exit **0**, **17 passed**, **0 failed**, **0 errors**, in **0.12s**. |
| Runtime harness command/scenario | **N/A — no live Discord/Supabase runtime boundary exists for this persistence-only unit.** The evidence is limited to pure model and mocked DB CRUD tests; no Discord API call, Supabase query, or migration application was executed. |
| Rollback boundary | Revert only `migrations/016_greeting_onboarding_channel.sql`, `bot/models/greeting_config.py`, `bot/core/db/greeting_db.py`, `tests/test_greeting_config.py`, and `tests/test_greeting_db.py`; restore only Unit 1 task checkboxes. Leave Phase 2/3 artifacts and unrelated pending features untouched. |

## Files Changed

| File | Action | What was done |
|---|---|---|
| `migrations/016_greeting_onboarding_channel.sql` | Created | Added the nullable, repeat-safe `onboardingChannelId` column. |
| `bot/models/greeting_config.py` | Modified | Added nullable onboarding-channel state and camelCase row serialization. |
| `bot/core/db/greeting_db.py` | Modified | Typed/documented the existing generic greeting CRUD for the expanded model payload. |
| `tests/test_greeting_config.py` | Modified | Added default, mapping, serialization, and round-trip coverage. |
| `tests/test_greeting_db.py` | Modified | Added configured/null onboarding persistence coverage. |

### PR2 Files Changed

| File | Action | What was done |
|---|---|---|
| `bot/locales/en.json` | Modified | Added English greeting card title/count and onboarding CTA keys without replacing unrelated locale edits. |
| `bot/locales/es.json` | Modified | Added Spanish greeting card title/count and onboarding CTA keys without replacing unrelated locale edits. |
| `bot/services/greeting_service.py` | Modified | Added cache-preserving onboarding dispatch behavior, caller-side translations, CTA composition, safe channel resolution, and translated renderer handoff arguments. |
| `bot/services/guild_service.py` | Modified | Added explicit GreetingService CRUD delegation without adding greeting fields to GuildConfig. |
| `tests/test_i18n.py` | Modified | Added ES/EN interpolation, fallback, namespace isolation, and shipped-locale completeness coverage. |
| `tests/test_greeting_service.py` | Modified | Added onboarding cache/CRUD, CTA, omission, goodbye, custom-message, and renderer handoff coverage. |
| `tests/test_guild_service.py` | Modified | Added GreetingService delegation and missing-dependency safety coverage. |

## Deviations and Issues

- Deviations from design: None — implementation matches the PR1 persistence design and does not implement service, locale, renderer, cog, Realtime, or dashboard behavior.
- Issues: No live Discord or Supabase runtime harness applies to this unit. The focused command uses `--no-cov` so the persistence evidence is not obscured by the repository-wide coverage threshold when running only these two files.
- No commits, staging, pushes, worktrees, migration applications, or unrelated artifact changes were performed.

### PR2 Deviations and Issues

- Deviations from design: None within tasks 2.1–2.7. Renderer redesign, cog wiring, Realtime behavior, and dashboard changes remain intentionally deferred to Phase 3.
- Issue: `uv run ruff check` passes for both modified production services. Running it across the three modified test files still reports two pre-existing `RUF012` mutable class-attribute findings in the existing `FakeHybridCmd.parameters` fixtures; those lines were not part of this unit's behavior change.
- No live Discord or Supabase runtime harness applies; the focused evidence intentionally uses mocked channels, image service, database, and delegation dependencies.

## Remaining Tasks

### Phase 2 — Locales and Services

- [x] 2.1 RED: i18n card/CTA resolution and interpolation tests
- [x] 2.2 RED: i18n fallback and placeholder namespace tests
- [x] 2.3 GREEN: add English and Spanish greeting locale keys
- [x] 2.4 RED: GreetingService cache/CTA behavior tests
- [x] 2.5 GREEN: implement GreetingService CRUD, translation, CTA, and renderer handoff
- [x] 2.6 RED: GuildService delegation tests
- [x] 2.7 GREEN: delegate greeting configuration to GreetingService

### Phase 3 — Renderer, Cog, and Dashboard

- [x] 3.1 RED: ImageService localized rendering and fallback tests
- [x] 3.2 GREEN: implement branded renderer inputs and fallbacks
- [x] 3.3 RED: GreetingsCog localized test/config command tests
- [x] 3.4 GREEN: wire localized cog behavior and onboarding status
- [x] 3.5 RED: Realtime onboarding-column invalidation tests
- [x] 3.6 GREEN: complete greeting-config CDC invalidation behavior
- [x] 3.7 RED: dashboard greeting action contract tests
- [x] 3.8 GREEN: persist and expose onboarding channel in the dashboard
- [x] 3.9 Final: run the full test suite

## Workload / PR Boundary

- Mode: stacked PR slice
- Current work unit: Unit 3 — Renderer, cog, Realtime, dashboard
- Boundary: starts at the approved PR2 slice and ends after tasks 3.1–3.9; excludes tickets, backups, integrity, CI, unrelated specs, and live migrations
- Estimated review budget impact: approximately 500 authored/untracked PR3 lines including focused tests; the high forecast remains handled by the approved `auto-chain` PR1 → PR2 → PR3 split

## PR2 Work Unit Evidence

| Evidence | Exact result |
|---|---|
| Focused test command | `uv run pytest --no-cov tests/test_i18n.py tests/test_greeting_service.py tests/test_guild_service.py -v` — exit **0**, **76 passed**, **0 failed**, **0 errors**, in **0.25s**. |
| Runtime harness command/scenario | **N/A — this unit has no live runtime boundary.** Discord channels, image handoff, cache, DB, and service delegation were exercised with mocks; no Discord API, Supabase query, migration application, or live bot startup was executed. |
| Rollback boundary | Revert only `bot/locales/en.json`, `bot/locales/es.json`, `bot/services/greeting_service.py`, `bot/services/guild_service.py`, `tests/test_i18n.py`, `tests/test_greeting_service.py`, `tests/test_guild_service.py`, and the cumulative task/progress evidence. Preserve PR1 migration/model/DB behavior. |

## Status Summary

**21/21 tasks complete.** PR1 tasks 1.1–1.5, PR2 tasks 2.1–2.7, and PR3 tasks 3.1–3.9 are complete; focused and full Python/dashboard evidence is green. Ready for verification.

## Bounded Ordinary-Review Correction

- **Review lineage:** `review-92ffe0d1d48c70f7`
- **Blocker:** `GreetingService` supplied `greeting_title` and `member_count_text`, but `ImageService.generate_greeting_card()` rejected both kwargs and raised `TypeError` for card-enabled dispatch.
- **Scope:** Added optional renderer inputs with `None` defaults; localized title/count text now use the existing Pillow text positions and layout. No premium redesign, guild-icon overlay, cog, dashboard, Realtime, or other Phase 3 work was implemented.
- **Phase 3 status:** Tasks 3.1 and 3.2 remain unchecked in `tasks.md`.

### Correction TDD Cycle Evidence

| Task | Test file | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|
| Bounded renderer compatibility correction | `tests/test_image_service.py` | ✅ Baseline: 20 passed | ✅ New supplied-string test first failed with the expected unexpected-keyword `TypeError`; layout-preservation assertion then failed until the existing username placement was retained. | ✅ `uv run pytest --no-cov tests/test_image_service.py::TestGenerateGreetingCard::test_supplied_localized_strings_are_rendered tests/test_image_service.py::TestGenerateGreetingCard::test_omitted_localized_strings_preserve_default_rendering -v` — exit 0, **2 passed** in **0.04s**. | ✅ Supplied localized title/count and omitted-argument defaults exercise distinct paths. | ✅ Preserved existing coordinates, PNG output, card-type fallback, and default English copy; `ruff check` passed. |

### Correction Work Unit Evidence

| Evidence | Exact result |
|---|---|
| Focused test command | `uv run pytest --no-cov tests/test_image_service.py tests/test_greeting_service.py tests/test_i18n.py tests/test_guild_service.py -v` — exit **0**, **98 passed**, **0 failed**, **0 errors**, in **0.43s**. |
| Runtime harness command/scenario | **N/A — this correction only changes a synchronous Pillow renderer and mocked/unit test seam; no live Discord or Supabase boundary was exercised.** |
| Rollback boundary | Revert only `bot/services/image_service.py` and the added renderer assertions in `tests/test_image_service.py`; preserve all PR1/PR2 paths and cumulative evidence. |

### Correction Files and Deviation

- `bot/services/image_service.py` — accepts optional localized title/count inputs while retaining backward-compatible defaults and the existing layout.
- `tests/test_image_service.py` — observes localized strings at the existing Pillow `draw.text` seam and verifies omitted-argument defaults.
- **Deviation:** Minimal compatibility correction only; no deviation beyond preserving the existing renderer layout while inserting supplied localized copy.

**Correction status:** Complete and bounded. At the time of this correction, **12/21 tasks were complete**; PR3 later completed the remaining Phase 3 tasks below.

## Bounded Genesis Correction — R3-001

- **Review lineage:** `review-92ffe0d1d48c70f7`; finding `R3-001`.
- **Scope:** Kept the correction inside `bot/services/greeting_service.py`, `tests/test_greeting_service.py`, and this progress artifact only. The helper first attempts the localized renderer contract, retries without `greeting_title`/`member_count_text` only for a matching unexpected-keyword `TypeError`, and re-raises unrelated `TypeError` instances.
- **Compatibility result:** The corrected renderer continues receiving localized strings; an old constrained renderer signature receives the legacy arguments without crashing.
- **Phase 3 status:** Tasks 3.1–3.9 remain unchecked in `tasks.md`; `image_service.py` and `tests/test_image_service.py` were not edited in this correction.

### R3-001 Correction TDD Cycle Evidence

| Task | Test file | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|
| R3-001 | `tests/test_greeting_service.py` | ✅ Baseline: `uv run pytest --no-cov tests/test_greeting_service.py -v` — **28 passed**. | ✅ Pre-helper constrained old-signature run exited 1 with the expected unexpected-keyword `TypeError`; unrelated renderer `TypeError` remained propagated. | ✅ `uv run pytest --no-cov tests/test_greeting_service.py::TestDispatchWelcome::test_resolvable_onboarding_channel_appends_localized_cta tests/test_greeting_service.py::TestDispatchWelcome::test_renderer_compatibility_fallback_and_error_propagation -v` — exit 0, **2 passed**. | ✅ Covered localized compatible handoff, old-signature fallback, and unrelated `TypeError` propagation. | ✅ `ruff check` passed; fallback is centralized and both welcome/goodbye dispatches use the same helper. |

### R3-001 Work Unit Evidence

| Evidence | Exact result |
|---|---|
| Focused test command | `uv run pytest --no-cov tests/test_greeting_service.py tests/test_image_service.py tests/test_i18n.py tests/test_guild_service.py -v` — exit **0**, **99 passed**, **0 failed**, **0 errors**, in **0.52s**. |
| Runtime harness command/scenario | **N/A — this bounded correction has no live runtime boundary.** The old/new renderer seams and dispatch path were exercised with mocked Discord/service dependencies; no Discord API or Supabase runtime was executed. |
| Rollback boundary | Revert only the compatibility helper/call-site changes in `bot/services/greeting_service.py`, the R3-001 assertions/seam in `tests/test_greeting_service.py`, and this cumulative evidence. Preserve PR1/PR2 behavior and all Phase 3 renderer artifacts. |

### R3-001 Files, Forecast, and Status

- `bot/services/greeting_service.py` — added the narrowly scoped keyword-mismatch fallback for both card dispatch paths.
- `tests/test_greeting_service.py` — added the constrained old-signature and unrelated-error coverage; strengthened the localized handoff assertion.
- **Line forecast:** exactly **50 authored changed lines** in the genesis code/test paths (`19` additions + `2` deletions in the service and `29` additions in the test), within the authorized correction budget.
- **Correction status:** Complete and bounded. At the time of this correction, **12/21 tasks were complete**; PR3 later completed the remaining Phase 3 tasks below.

## PR3 — Unit 3 TDD Cycle Evidence

| Task | Test file | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| 3.1 | `tests/test_image_service.py` | Unit | ✅ Baseline: `uv run pytest --no-cov tests/test_image_service.py` — 22 passed | ✅ Added supplied guild-icon/localized-copy, missing-asset, and fetch-failure assertions before the renderer changes; the new signature/fallback assertions failed as expected. | ✅ Focused PR3 run — renderer tests passed with branded output and safe fallbacks. | ✅ Covered supplied assets, null assets, fetch exceptions, localized text, default arguments, and deterministic repeated output. | ✅ Extracted safe asset fetching and circular asset/placeholder drawing; existing rank-card path unchanged. |
| 3.2 | `bot/services/image_service.py` | Unit | ✅ Same renderer baseline | ✅ Renderer contract tests failed before `guild_icon_url`, guild identity drawing, and placeholders existed. | ✅ `uv run pytest --no-cov tests/test_image_service.py tests/test_greetings_cog.py tests/test_realtime.py -v` — 133 passed. | ✅ Both asset-present and asset-missing branches produce valid PNGs; supplied strings and backward-compatible defaults remain distinct. | ✅ Kept Pillow synchronous and deterministic; async callers continue to use `asyncio.to_thread()`. |
| 3.3 | `tests/test_greetings_cog.py` | Mocked Discord integration | ✅ Baseline cog suite: 43 passed | ✅ Added Spanish test-card handoff and onboarding-status assertions before cog wiring; both failed because localized kwargs/status were absent. | ✅ Focused PR3 run — 133 passed. | ✅ Welcome localized handoff, guild icon handoff, configured onboarding status, missing-channel status, admin, and error paths covered. | ✅ Reused existing command guard/embed patterns. |
| 3.4 | `bot/cogs/greetings.py` | Mocked Discord integration | ✅ Same cog baseline | ✅ Production wiring followed the failing command assertions. | ✅ Focused PR3 run — 133 passed; both test commands resolve localized title/count strings and use `asyncio.to_thread()`. | ✅ Welcome and goodbye paths use distinct title keys; config status is only added to the welcome view. | ✅ Added bounded cached guild-icon URL resolution with safe fallback. |
| 3.5 | `tests/test_realtime.py` | Mocked Realtime integration | ✅ Baseline Realtime suite: 64 passed | ✅ Added the onboarding-column UPDATE CDC test first. The existing generic `greeting_config` CDC branch already satisfied it, so the baseline was green rather than producing a new failure. | ✅ Focused PR3 run — 133 passed. | ✅ Covered onboarding UPDATE, existing greeting INSERT/DELETE, nested SDK payloads, self-echo filtering, and ticket-note resolution. | ✅ Preserved the established table-generic invalidation path; no redundant special-case branch was introduced. |
| 3.6 | `bot/core/realtime.py` | Mocked Realtime integration | ✅ Same Realtime baseline | ✅ The task-specific test was written before final PR3 verification; the existing subscriber already invalidated all `greeting_config` rows by `guildId`. | ✅ Focused PR3 run — 133 passed; onboarding CDC invalidates `{guild_id}:config` through `TTLCache.invalidate_guild()`. | ✅ CamelCase `onboardingChannelId` UPDATE and existing DELETE/nested payload cases both invalidate correctly. | ✅ No production change was needed because the existing four-table CDC registration and generic handler already matched the design. |
| 3.7 | `dashboard/__tests__/lib/actions/greeting-actions.test.ts` | Unit/integration with mocked Supabase | ✅ Baseline action suite: 18 passed | ✅ Added valid/null/invalid onboarding and no-webhook assertions before action changes; payload/validation behavior was absent. | ✅ `npm test -- __tests__/lib/actions/greeting-actions.test.ts __tests__/app/greeting-page.test.tsx` — 23 passed. | ✅ Valid snowflake, empty-to-null, invalid ID, authenticated admin, and no global `fetch()` call covered. | ✅ Reused the existing auth, validation, upsert, and revalidation pipeline. |
| 3.8 | `dashboard/__tests__/app/greeting-page.test.tsx`, dashboard production paths | Unit/integration | ✅ Existing dashboard test suite available; new page test was added before the page control. | ✅ New page test failed before the nullable field/control existed; action tests also failed before parse/upsert wiring. | ✅ `npm test` — 17 files, 240 passed; `npm run build` compiled, type-checked, linted, and generated all routes successfully. | ✅ New-config null default and populated onboarding ID page states are covered. | ✅ Added one existing `ConfigForm` text control; no webhook/API route or unrelated dashboard page was introduced. |
| 3.9 | Full regression verification | Repository | ✅ Focused Python baseline: 127 passed; dashboard action baseline: 18 passed | ✅ All PR3 RED tests were written before their corresponding production changes. | ✅ `uv run pytest -v` — 1,745 passed, 3 skipped, exit 0; dashboard `npm test` — 17 files/240 passed, exit 0. | ✅ Python focused suite: 133 passed; dashboard focused suite: 2 files/23 passed; dashboard `npx tsc --noEmit` exit 0; `npm run build` exit 0. | ✅ `ruff check` passed for modified production Python files; no unrelated files were changed by PR3. |

### PR3 Test Summary

- **Total tests written**: 12 new focused Python/dashboard scenarios, including one dashboard page test file covering 2 scenarios.
- **Total focused tests passing**: Python 133/133; dashboard 23/23.
- **Full regression**: Python 1,745 passed, 3 skipped; dashboard 240 passed across 17 files.
- **Layers used**: Python unit and mocked Discord/Realtime integration; dashboard unit and mocked Supabase/Server Component integration; E2E unavailable by project configuration.
- **Approval tests**: None — PR3 adds behavior; the preserved renderer compatibility correction remains covered by its prior approval-compatible assertions.
- **Pure functions/helpers**: Safe guild/member asset resolution and circular placeholder rendering helpers; existing Realtime generic invalidation path retained.

### PR3 Work Unit Evidence

| Evidence | Exact result |
|---|---|
| Focused Python test command | `uv run pytest --no-cov tests/test_image_service.py tests/test_greetings_cog.py tests/test_realtime.py -v` — exit **0**, **133 passed**, **0 failed**, **0 errors**, in **0.74s**. |
| Focused dashboard test command | `npm test -- __tests__/lib/actions/greeting-actions.test.ts __tests__/app/greeting-page.test.tsx` from `dashboard/` — exit **0**, **2 files**, **23 passed**, **0 failed**. |
| Full Python regression | `uv run pytest -v` — exit **0**, **1,745 passed**, **3 skipped**, coverage **88.84%**. |
| Full dashboard regression | `npm test` from `dashboard/` — exit **0**, **17 files**, **240 passed**, **0 failed**. Existing unrelated React `act(...)` warnings appeared in ticket-page tests; no test failed. |
| Dashboard type/build checks | `npx tsc --noEmit` — exit **0**; `npm run build` — exit **0**, production build compiled, type-checked, and generated the greeting route. |
| Dashboard lint script | `npm run lint` / `CI=1 npm run lint` did not reach a result: the repository's `next lint` script opened the interactive ESLint configuration prompt and timed out. `npm run build` independently completed its lint/type validation successfully. |
| Runtime harness command/scenario | **N/A — no live runtime boundary was authorized.** Discord, Supabase Realtime, and Server Action behavior were exercised through mocked integration tests; no Discord API calls, live Supabase writes, webhook calls, or migration application were performed. |
| Rollback boundary | Revert only PR3 paths: `bot/services/image_service.py`, `bot/services/greeting_service.py` renderer-icon handoff compatibility, `bot/cogs/greetings.py`, dashboard greeting types/action/page, dashboard greeting focused tests/helpers, `tests/test_image_service.py`, `tests/test_greetings_cog.py`, `tests/test_realtime.py`, and the cumulative `tasks.md`/`apply-progress.md` evidence. Preserve PR1/PR2 model, migration, locale, service, and cache behavior. |

### PR3 Files Changed

| File | Action | What was done |
|---|---|---|
| `bot/services/image_service.py` | Modified | Added optional guild-icon input, premium hierarchy/accent treatment, guild identity text, circular asset rendering, deterministic placeholders, and exception-safe asset fetching while preserving localized/default text compatibility. |
| `bot/services/greeting_service.py` | Modified | Passed cached guild icon URLs to the renderer and extended the bounded old-renderer compatibility fallback to remove the new optional keyword. |
| `bot/cogs/greetings.py` | Modified | Resolved localized test-card title/count strings, guild icon input, and exposed onboarding status in welcome configuration output. |
| `tests/test_image_service.py` | Modified | Added localized identity, premium output, deterministic fallback, and avatar-failure tests. |
| `tests/test_greetings_cog.py` | Modified | Added localized test-card handoff and onboarding-status tests. |
| `tests/test_realtime.py` | Modified | Added onboarding-column CDC cache invalidation coverage. |
| `dashboard/lib/types.ts` | Modified | Added nullable `onboardingChannelId` to `GreetingConfig`. |
| `dashboard/lib/actions/greeting-actions.ts` | Modified | Parsed, validated, upserted, and revalidated nullable onboarding channel without a webhook. |
| `dashboard/app/(authenticated)/guilds/[guildId]/greeting/page.tsx` | Modified | Added an existing-pattern text control with null default and setup hint. |
| `dashboard/__tests__/lib/actions/_test-helpers.ts` | Modified | Exposed greeting upsert spy for payload assertions. |
| `dashboard/__tests__/lib/actions/greeting-actions.test.ts` | Modified | Covered valid/null/invalid onboarding persistence and no-webhook behavior. |
| `dashboard/__tests__/app/greeting-page.test.tsx` | Created | Covered null and configured page control states. |

### PR3 Deviations and Issues

- **Deviation:** `bot/services/greeting_service.py` was necessarily included to pass the new guild icon through live welcome/goodbye dispatch and to preserve the previously recorded old-renderer compatibility correction. This remains inside the greeting renderer handoff boundary; no unrelated service behavior changed.
- **Realtime:** No production Realtime code change was needed. The existing subscriber already registered `greeting_config` and invalidated the guild cache generically by `guildId`; the new onboarding UPDATE test proves that path.
- **Migration prerequisite:** `migrations/016_greeting_onboarding_channel.sql` remains additive and must be applied before deploying dashboard writes/application changes. It was **not** applied to live Supabase in this phase.
- **Lint issue:** The standalone dashboard `next lint` package script is interactive/deprecated and did not complete. The successful production build performed its own lint/type validation; no project lint configuration was changed.
- **No commits, staging, pushes, worktrees, live migrations, webhook calls, or unrelated feature-file edits were performed.**

## Final Cumulative Status

**21/21 tasks complete.** PR1, PR2, the bounded renderer compatibility correction, the bounded R3-001 correction, and PR3 are preserved cumulatively. Implementation and artifacts are coherent; ready for `sdd-verify`. 
