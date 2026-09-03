```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:a53d2efcf7019bc75726b158cb702483a88ce0f321862d23d273f5ab4e7c0ae2
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 11/11
scenarios: 51/51
test_command: "uv run pytest -q --cov=bot --cov-fail-under=80 --randomly-seed=42"
test_exit_code: 0
test_output_hash: sha256:f928a40422a322c92d36600740bf6a12633dfd88f8b99f8363400b704c9b6603
build_command: "make ci"
build_exit_code: 0
build_output_hash: sha256:2d12ce61562bc9315226e85ef5054d2aee79d3b644a3c32524b8ae0ce71670dc
```

## Verification Report

**Change**: greeting-templates  
**Verification revision**: Rev3  
**Version**: N/A  
**Mode**: Strict TDD  
**Implementation revision**: `7d043ed1702be28be2210b6d13d011cd76cfdcda`

### Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 12 |
| Tasks complete | 12 |
| Tasks incomplete | 0 |
| Spec documents inspected | 5/5 (four delta specs plus one no-delta decision) |
| Requirements complete | 11/11 |
| Scenarios compliant | 51/51 |

All proposal, specification, design, task, implementation, test, and launch-provided remediation evidence was inspected. Native heading counts are authoritative: `greeting-config` 4 requirements/18 scenarios, `i18n-system` 1/6, `setup-panel` 2/10, `welcome-goodbye` 4/17, and `brand-tokens/README.md` 0/0. All task checkboxes are complete.

### Rev2 CRITICAL Closure

| Rev2 finding | Status | Fresh Rev3 proof |
|--------------|--------|------------------|
| #1 FOCUSED-GATE | ✅ Resolved | `tasks.md:28,52` now defines the focused setup command with `--no-cov`; `uv run pytest -k setup_module -q --no-cov` exited 0 with 55 passed/3,008 deselected (`9d5215092f54e301da603cf4ce6e20ffb7994cb71b54467b2c53b6f7a59f3693`). |
| #2 TAUTOLOGICAL-ASSERTION | ✅ Resolved | `tests/test_setup_module_welcome.py:375,385` captures non-null `goodbye_before="minimal_light"` before the action and asserts exact equality afterward. The baseline closure pair passed 2/2 (`b25dad388082254d71bd118221bad8a7d1fa65013d0628aeb9cede5f635e00a4`). A verifier-only mutation to `"gaming_neon"` produced the expected assertion failure (`3530af8a41c9df54e95c70ecd3c0557172b96039c8d3c34fae9568fbcb1bbb11`), proving falsifiability. |
| #3 STATIC-SOURCE-STAND-IN | ✅ Resolved | `tests/test_setup_panel_pickers.py:242-286` executes the real `NebulosaBot.setup_hook`, captures `add_view`, requires an actual `SetupPanelView`, and asserts both picker custom IDs. The baseline closure pair passed 2/2; replacing registrations with plain `discord.ui.View` objects produced the expected failure (`a4ee76ab2f7eae4c042af101b55fb8d9ab4ee6fdfee2845e7f30f9a767d17c6a`). |

The two fault-injection commands intentionally exited 1 because the repaired assertions caught the injected defects. They are negative test-integrity probes, not failing candidate checks.

### Build & Tests Execution

**Build**: ✅ Passed

| Command | Exit | Result | Output SHA-256 |
|---------|------|--------|----------------|
| `make ci` | 0 | Ruff check/format, ty, Tach internal/external, and two complete coverage runs passed; each test run had 3,044 passed/19 skipped and 81.78% coverage | `2d12ce61562bc9315226e85ef5054d2aee79d3b644a3c32524b8ae0ce71670dc` |
| `uv run ty check bot/ tests/` | 0 | All checks passed | `82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18` |
| `uv run ruff check bot/ tests/` | 0 | All checks passed | `82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18` |
| `uv run ruff format --check bot/ tests/` | 0 | 270 files already formatted | `02b01aaaeed47ace86d3000f8bbcd2951e8f78c28de924ce555b4aae3dd22e98` |
| `uv run vulture bot/ --min-confidence 80` | 0 | Empty output, matching the clean baseline | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `uv run tach check && uv run tach check-external` | 0 | Internal modules and external dependencies validated | `eaff7a2ebc976e27f8799ba5a31c4f0058919ef45dd33f9d6416b76cef21da74` |

**Primary tests**: ✅ 3,044 passed / ❌ 0 failed / ⚠️ 19 skipped

| Command | Exit | Result | Output SHA-256 |
|---------|------|--------|----------------|
| `uv run pytest -q --cov=bot --cov-fail-under=80 --randomly-seed=42` | 0 | 3,044 passed, 19 skipped, 19 inherited warnings; 81.78% | `f928a40422a322c92d36600740bf6a12633dfd88f8b99f8363400b704c9b6603` |
| `uv run pytest -q --no-cov --randomly-seed=777` | 0 | 3,044 passed, 19 skipped, 19 inherited warnings | `8ebc96793a321a11891bf7fb0f947b7ca783f9a1c163c5a7257cdf67b15bf5f3` |
| `uv run pytest tests/test_setup_module_welcome.py tests/test_setup_panel_pickers.py tests/test_preview_resolved_template.py -q --no-cov` | 0 | 30 remediation and closure tests passed | `d066046c9a805cd0aa8dda13d2d69717bbb654406dd05236dc3afcbbe70cef38` |
| `uv run pytest -k setup_module -q --no-cov` | 0 | 55 passed, 3,008 deselected, 19 inherited warnings | `9d5215092f54e301da603cf4ce6e20ffb7994cb71b54467b2c53b6f7a59f3693` |
| Two exact Rev2 closure node IDs | 0 | Tautology replacement and real setup-hook registration proof passed 2/2 | `b25dad388082254d71bd118221bad8a7d1fa65013d0628aeb9cede5f635e00a4` |
| `uv run pytest tests/test_i18n_key_coverage.py -q --no-cov` | 0 | 17 passed | `5861f86931c5de3747c7570eaa6433585fb29d48e950d10c932927ceefb29d78` |
| `uv run pytest tests/test_migrations.py -q --no-cov` (run 1) | 0 | 65 passed | `7bd0e1ca62a401065bc714f248cb249bb9efb5218b12cb672b77a0ad96329e39` |
| `uv run pytest tests/test_migrations.py -q --no-cov` (run 2) | 0 | 65 passed | `7bd0e1ca62a401065bc714f248cb249bb9efb5218b12cb672b77a0ad96329e39` |
| `uv run pytest --collect-only -q --no-cov` | 0 | 3,063 tests collected | `0a9aa9b5fe3790817eb00a73afb6a2efd57df7f06a323b4871045f7a04ee4a87` |

**Coverage**: 81.78% / threshold 80% → ✅ Above

Fresh ledger: **175 Python test files / 62,384 lines / 3,063 collected / 3,044 passed / 19 skipped / 81.78% seed-42 coverage**. File/line ledger hash: `6ceb7c55e101e95f7903f9a94e7691afb79aaa3d6e5f61405c35167639b56290`. The 19 warnings are inherited discord.py `TextInput.label` deprecations in ticket setup tests.

### Runtime Diagnostic Evidence

| Probe | Exit | Observation | Output SHA-256 |
|-------|------|-------------|----------------|
| Real closure node IDs | 0 | Welcome selection preserves the captured opposite-kind value; real setup-hook registers a `SetupPanelView` carrying both picker IDs | `b25dad388082254d71bd118221bad8a7d1fa65013d0628aeb9cede5f635e00a4` |
| Opposite-kind defect injection | 1 expected | Replacing saved goodbye with `gaming_neon` fails exact equality against captured `minimal_light` | `3530af8a41c9df54e95c70ecd3c0557172b96039c8d3c34fae9568fbcb1bbb11` |
| Registration impostor injection | 1 expected | Capturing only plain `discord.ui.View` objects leaves no `SetupPanelView` and fails the registration assertion | `a4ee76ab2f7eae4c042af101b55fb8d9ab4ee6fdfee2845e7f30f9a767d17c6a` |
| Greetings cog invariance | 0 | `git diff --exit-code e20c515^..HEAD -- bot/cogs/greetings.py` is empty | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

### TDD Compliance

| Check | Result | Details |
|-------|--------|---------|
| TDD evidence reported | ✅ | Launch-provided cumulative apply evidence (Engram `#5080`) contains well-formed R1 and Rev2 TDD cycle tables |
| All implementation tasks have tests | ✅ | 9/9 S1-S3 implementation tasks and 3/3 remediation rows map to committed tests |
| RED confirmed | ✅ | Apply evidence records RED chronology; fresh opposite-kind and registration defect injections both fail the repaired assertions |
| GREEN confirmed | ✅ | 30/30 remediation tests and 3,044/3,044 executed full-suite tests pass under both seeds |
| Triangulation adequate | ✅ | Registry, persistence, interaction routing, setup-hook registration, PNG preview aliases, fallback behavior, and i18n are tested at distinct layers |
| Safety net recorded | ✅ | Seeds 42 and 777 both pass; total coverage is 81.78% |

**TDD compliance**: 6/6 evidence checks passed.

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit/static contract | 61 authored change cases | 8 changed test files | pytest, Pillow, AST/source guards |
| Mocked interaction integration | 21 authored change cases | 4 changed test files | pytest-asyncio, discord.py mocks, real `setup_hook` |
| Verifier fault-injection diagnostics | 2 probes | verifier-only temporary copies | pytest mutation probes |
| E2E against Discord/Supabase | 0 | 0 | Not used |

The change authored 82 committed cases across 11 files before accounting for consolidated legacy coverage. The net suite collection is 3,063.

### Changed File Coverage

| File | Statements covered | Line % | Rating |
|------|--------------------|--------|--------|
| `bot/core/db/greeting_db.py` | 35/35 | 100.00% | ✅ Excellent |
| `bot/models/greeting_config.py` | 26/26 | 100.00% | ✅ Excellent |
| `bot/services/greeting_renderer.py` | 127/130 | 97.69% | ✅ Excellent |
| `bot/services/greeting_service.py` | 142/155 | 91.61% | ✅ Acceptable |
| `bot/services/schema_inventory.py` | 168/202 | 83.17% | ✅ Acceptable |
| `bot/services/live_catalog.py` | 123/172 | 71.51% | ⚠️ Low |
| `bot/views/setup_modules/goodbye.py` | 160/239 | 66.95% | ⚠️ Low |
| `bot/views/setup_modules/welcome.py` | 167/283 | 59.01% | ⚠️ Low |
| `bot/views/setup_panel.py` | 167/269 | 62.08% | ⚠️ Low |

**Weighted changed-Python-file coverage**: 73.79% (1,115/1,511 statements). Total project coverage remains above the required threshold.

### Assertion Quality

| File | Line | Assertion gap | Severity |
|------|------|---------------|----------|
| `tests/test_setup_panel_pickers.py` | 193-198 | The test named “keeps panel controls” checks only that the edited `view` is non-null; it does not itself inspect `view.children`. Stronger neighboring runtime tests and the setup-hook proof cover the actual picker IDs. | WARNING |

**Assertion quality**: 0 CRITICAL, 1 WARNING. The two Rev2 CRITICAL assertion defects are closed and independently falsifiable.

### Spec Compliance Matrix

| Requirement | Scenario | Passing runtime test/evidence | Result |
|-------------|----------|-------------------------------|--------|
| WG-1 Registry | Registry contains four templates | `TestRegistryFourTemplates::test_registry_enumerates_exactly_four_keys` | ✅ COMPLIANT |
| WG-1 Registry | Unknown falls back to default | `TestUnknownFallback::test_unknown_template_id_renders_default_bytes` | ✅ COMPLIANT |
| WG-1 Registry | gaming_neon byte identity | Portable neon alias/byte and token pixel tests | ✅ COMPLIANT |
| WG-1 Registry | Renderer t()-free and card-image-only | `TestRendererTFree` and renderer contract tests | ✅ COMPLIANT |
| WG-2 Selection | Welcome resolves per-kind ID | `TestSelectTemplateFallbackChain::test_welcome_resolves_welcome_template_id` | ✅ COMPLIANT |
| WG-2 Selection | Goodbye resolves per-kind ID | `TestSelectTemplateFallbackChain::test_goodbye_resolves_independently` | ✅ COMPLIANT |
| WG-2 Selection | Fallback to legacy themeId | `test_fallback_to_legacy_theme_id_when_kind_null` | ✅ COMPLIANT |
| WG-2 Selection | Fallback to default | `test_fallback_to_default_when_both_absent` | ✅ COMPLIANT |
| WG-3 Interface | Service depends on interface | `TestProtocolOnlyConstructor` and dispatch tests | ✅ COMPLIANT |
| WG-3 Interface | Receives translated strings only | Localized dispatch tests and renderer AST guard | ✅ COMPLIANT |
| WG-3 Interface | Accepts template_id and legacy alias | `TestDualParamRender` | ✅ COMPLIANT |
| WG-3 Interface | Null/default renders default | `TestUnknownFallback::test_none_renders_default` and default dispatch | ✅ COMPLIANT |
| WG-3 Interface | Unknown ID renders default | `test_unknown_template_id_renders_default_bytes` | ✅ COMPLIANT |
| WG-4 Pillow | Default uses brand tokens | `TestGreetingRendererBrandTokens` | ✅ COMPLIANT |
| WG-4 Pillow | Neon uses ACCENT_A/B | Neon pixel/token tests | ✅ COMPLIANT |
| WG-4 Pillow | Sunset/minimal use existing tokens | `test_sunset_minimal_use_brand_tokens_only` | ✅ COMPLIANT |
| WG-4 Pillow | Render runs off event loop | `test_dispatch_greeting_runs_renderer_through_to_thread` | ✅ COMPLIANT |
| GC-1 Migration | Existing rows remain valid | Migration 030 preservation/backfill tests | ✅ COMPLIANT |
| GC-1 Migration | New guild defaults null | `TestPerKindTemplateFields::test_default_new_guild_fields_are_null` | ✅ COMPLIANT |
| GC-1 Migration | IF NOT EXISTS guards rerun | `TestMigration030::test_is_idempotent_add_column_if_not_exists`; migration suite passed twice | ✅ COMPLIANT |
| GC-1 Migration | COALESCE backfills legacy | `test_coalesce_backfills_nulls_from_legacy_theme_id` | ✅ COMPLIANT |
| GC-2 Dual-write | Welcome resolves new column | `test_welcome_resolves_welcome_template_id` | ✅ COMPLIANT |
| GC-2 Dual-write | Goodbye resolves independently | `test_goodbye_resolves_independently` | ✅ COMPLIANT |
| GC-2 Dual-write | Legacy fallback | `test_fallback_to_legacy_theme_id_when_kind_null` | ✅ COMPLIANT |
| GC-2 Dual-write | Null/unknown fallback | Default and unknown fallback tests | ✅ COMPLIANT |
| GC-2 Dual-write | Legacy themeId persisted | `TestWelcomeWinsDualWrite` and DB payload tests | ✅ COMPLIANT |
| GC-3 CDC | Welcome update invalidates cache | Greeting-config table-level CDC invalidation tests | ✅ COMPLIANT |
| GC-3 CDC | Goodbye update invalidates cache | Greeting-config table-level CDC invalidation tests | ✅ COMPLIANT |
| GC-3 CDC | Realtime covers new columns | Table subscription and whole-guild invalidation tests | ✅ COMPLIANT |
| GC-4 Columns | New-guild defaults | Config default tests | ✅ COMPLIANT |
| GC-4 Columns | Onboarding round-trip | Existing onboarding round-trip tests | ✅ COMPLIANT |
| GC-4 Columns | updatedAt round-trip | Existing updatedAt round-trip tests | ✅ COMPLIANT |
| GC-4 Columns | theme_id round-trip | `TestThemeIdRoundTrip` | ✅ COMPLIANT |
| GC-4 Columns | welcome_template_id round-trip | `TestPerKindRoundtrip` | ✅ COMPLIANT |
| GC-4 Columns | goodbye_template_id round-trip | `TestPerKindRoundtrip` | ✅ COMPLIANT |
| SP-1 Picker | Welcome picker has four options | Welcome picker and production-panel option tests | ✅ COMPLIANT |
| SP-1 Picker | Goodbye picker has four options | Goodbye picker and production-panel option tests | ✅ COMPLIANT |
| SP-1 Picker | Selecting welcome persists | Production-panel callback plus exact captured opposite-kind assertion | ✅ COMPLIANT |
| SP-1 Picker | Selecting goodbye persists | Goodbye callback and kind-independence tests | ✅ COMPLIANT |
| SP-1 Picker | Missing permission denied | Module and production-panel denial tests | ✅ COMPLIANT |
| SP-1 Picker | render_async shows both labels | Welcome and goodbye template-label tests | ✅ COMPLIANT |
| SP-2 Preview | Welcome resolved template card | `TestWelcomePreviewResolvedTemplate` | ✅ COMPLIANT |
| SP-2 Preview | Goodbye resolved template card | `TestGoodbyePreviewResolvedTemplate` | ✅ COMPLIANT |
| SP-2 Preview | Unknown preview falls back | `test_preview_unknown_template_resolves_default_with_no_raise` | ✅ COMPLIANT |
| SP-2 Preview | Missing channel is safe | Welcome and goodbye no-channel tests | ✅ COMPLIANT |
| I18N-1 | All sixteen keys resolve | Two-locale parameterized resolution test | ✅ COMPLIANT |
| I18N-1 | Missing key reports callsite | `test_scanner_reports_missing_key_with_callsite` | ✅ COMPLIANT |
| I18N-1 | Picker labels use t() | Both picker localization tests | ✅ COMPLIANT |
| I18N-1 | Renderer stays t()-free | `TestRendererTFree` and AST invariant | ✅ COMPLIANT |
| I18N-1 | Locale key sets agree | `test_both_locales_define_identical_key_sets` | ✅ COMPLIANT |
| I18N-1 | Locale fallback chain remains | Existing i18n fallback tests and both-locale coverage | ✅ COMPLIANT |

**Compliance summary**: 51/51 scenarios compliant.

### Correctness (Static Evidence)

| Requirement group | Status | Notes |
|-------------------|--------|-------|
| Four-template procedural registry | ✅ Implemented | Exact registry, unknown fallback, existing brand tokens, and translation-free renderer |
| Per-kind selection and dual-write | ✅ Implemented | Nullable model fields, welcome-wins legacy mirror, independent resolution, DB projection, and cache invalidation |
| Migration 030 | ✅ Structurally implemented | Guarded additive DDL, `COALESCE` backfill, `WHERE IS NULL`, and rollback comment |
| Setup-panel picker availability | ✅ Implemented | Both static custom IDs are attached and a real setup-hook registration is executed in test |
| Selection persistence | ✅ Implemented | Both callback paths save per-kind values; exact opposite-kind preservation is now falsifiable |
| Preview aliases | ✅ Implemented | Welcome/goodbye paths pass resolved IDs as both `template_id` and `theme_id` via `asyncio.to_thread` |
| Sixteen locale keys | ✅ Implemented | Both locales pass symmetry and literal-key coverage guards |
| Greetings cog invariance | ✅ Preserved | Empty diff from the S1 parent through Rev3 |

### Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| Code-owned registry in renderer | ✅ Yes | Four dataclass-backed entries, procedural Pillow, existing brand tokens only |
| Per-kind resolver and renderer injection | ✅ Yes | Service owns policy; dispatch runs renderer off-loop |
| Nullable columns plus one-cycle dual-write | ✅ Yes | Model, DB projection, and migration align |
| Persistent StringSelect rerouted through setup panel | ✅ Yes | Real setup-hook test proves registered view type and both IDs |
| Preview forwards both resolved aliases | ✅ Yes | Welcome, goodbye, welcome-wins, and unknown fallback tests pass |
| Sixteen t() keys; renderer translation-free | ✅ Yes | Locale and source guards pass |
| Review/line forecast | ⚠️ Deviation accepted for this verification | Suite is 62,384 lines versus the permanent `<61,480` ceiling; additions were authorized for this change but remain governance debt |

### Quality Metrics

| Metric | Result |
|--------|--------|
| Full-suite pass rate | 100% of executed tests (3,044 passed, 0 failed; 19 skipped) |
| Seed stability | ✅ Seeds 42 and 777 passed |
| Total coverage | 81.78% (threshold 80%) |
| Weighted changed-file coverage | 73.79% |
| Remediation suite | 30/30 passed |
| Focused setup gate | 55/55 passed with `--no-cov` |
| Migration Python suite repeatability | 65/65 passed twice |
| Static/build gates | ✅ All passed |
| Rev2 test-integrity defects | ✅ Both closed with negative fault-injection proof |

### Issues Found

**CRITICAL**

None.

**WARNING**

1. **Suite governance ceiling** — Fresh ledger is 175 files / 62,384 lines / 3,063 collected / 81.78%. The line count is 904 above the permanent `<61,480` ceiling. The additions were approved within this change's delivery context, so this is recorded as non-blocking governance debt.
2. **Changed-file coverage** — Weighted coverage across changed Python files is 73.79%; `welcome.py` 59.01%, `setup_panel.py` 62.08%, `goodbye.py` 66.95%, and `live_catalog.py` 71.51% are below 80%. Total project coverage remains 81.78% and passes the configured gate.
3. **Migration proof depth** — Migration 030 has guarded structural tests and `tests/test_migrations.py` passed twice, but the SQL was not applied twice against a live PostgreSQL/Supabase database during verification.
4. **Weak retained-controls assertion** — `tests/test_setup_panel_pickers.py:193-198` verifies only that the edited view is non-null. Stronger adjacent tests prove both custom IDs and real setup-hook registration, so scenario compliance is unaffected.

**SUGGESTION**

1. Reduce the test suite below the permanent line ceiling in a dedicated governance change rather than weakening this feature's behavioral coverage.
2. Execute migration 030 twice against an isolated PostgreSQL/Supabase test database before production rollout.
3. Strengthen the retained-controls test to assert the selected picker ID exists in `view.children`.

### Verdict

**PASS WITH WARNINGS**

All 11 requirements and 51 scenarios are covered by passing runtime tests. All three Rev2 CRITICAL findings are independently closed; no blocking defect remains. The four standing warnings are non-blocking governance, coverage-depth, migration-depth, and assertion-strength risks.
