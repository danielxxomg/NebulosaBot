```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:945b7e8a1ed1d6e0701c9a471d7fa12f1245f067a587e495e7d179ee98ae4192
verdict: fail
blockers: 5
critical_findings: 5
requirements: 0/11
scenarios: 22/44
test_command: uv run pytest -q
test_exit_code: 0
test_output_hash: sha256:81c5d8a510d9d933a7060de236a45ef5bf74501372221db9d3a4bcd6ab0e8047
build_command: python -m py_compile bot/__main__.py
build_exit_code: 0
build_output_hash: sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

## Verification Report

**Change**: cleanup-stability (S1 L3)
**Version**: S1 L3
**Mode**: Strict TDD (re-verification after remediation)
**Head**: `9938429aa40c20f2b5f4e6d035476db0986d4779`
**Evidence revision**: `sha256:945b7e8a1ed1d6e0701c9a471d7fa12f1245f067a587e495e7d179ee98ae4192` (`git archive --format=tar HEAD`)
**Previous failed evidence**: `sha256:9b8529d2ac221bc357427378a9119eed74243ac851afbb88a20ccacdbe51e598`
**Remediation diff**: `d826654..9938429`, 264 additions/deletions

### Completeness

| Artifact / metric | Result |
|---|---|
| Proposal | Present; updated S1 gate deferrals and review-budget interpretation |
| Specs | Present; 7 spec files, 11 requirements, 44 scenarios |
| Design | Present |
| Exploration | Present |
| Tasks | 19/19 checkboxes complete; native status reports 19/19 |
| Apply progress | Present; original five work units plus remediation evidence |
| Verification report | Previous report read; this candidate replaces the worktree copy after admission |
| Scope | Repository-local action context; allowed edit root is the repository |

### Build and tests execution

**Build: PASS**

```text
python -m py_compile bot/__main__.py
exit 0; exact output is empty
output_hash: sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

**Full tests: PASS**

```text
uv run pytest -q
1814 passed, 3 skipped in 13.16s
coverage: 88.61% (threshold 75%)
exit 0
output_hash: sha256:81c5d8a510d9d933a7060de236a45ef5bf74501372221db9d3a4bcd6ab0e8047
```

**Focused remediation/config tests: PASS**

```text
uv run pytest tests/test_git_hygiene.py tests/test_pr2_context_cache_dry.py tests/test_pr3_inventory.py tests/test_pr3_service_role_rls.py tests/test_precommit_config.py tests/test_ci_config.py tests/test_ruff_config.py tests/test_mypy_config.py --no-cov -q
96 passed in 0.24s
exit 0
output_hash: sha256:e35dbc3b8f19626b7bd291c3de6cd0f883baa614e614c1c86aded1981bf73f70
```

**Quality gates**

| Gate | Exit | Evidence |
|---|---:|---|
| `uv run ruff check bot/ tests/` | 0 | `All checks passed!`; `sha256:82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18` |
| `uv run ruff format --check bot/ tests/` | 0 | `149 files already formatted`; `sha256:7a340da38ae65b1fde7d1e27b294de067e2bd0ac37ef92c9f1edbe0cafbed9ba` |
| `uv run mypy bot/` | 0 | `Success: no issues found in 67 source files`; `sha256:5bffadce8703c13cc5b58128f78b6683cf364d25c5ebace94758f720bc10cfc7` |
| `uv run bandit -r bot/ -c pyproject.toml --severity-level medium` | 0 | 0 medium/high issues, 92 low; `sha256:b700254eccc686ba9df0cbf59ab033e2c6729ca40c105fde8e05d2f32e9b67d4` |
| `python -m py_compile bot/__main__.py` | 0 | Empty output; `sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `uv run --with pre-commit pre-commit run --all-files` | 0 | All hooks passed, including GGA; `sha256:062ef3c40216571ab57454eb1b49af63cea50e11877b22181597531fc2b335f1` |
| `uv run ruff --version` | 0 | `ruff 0.15.20` |
| `uv run mypy bot/ tests/` (diagnostic only) | 1 | 28 errors in 7 test files; `sha256:46dbe8f910ee5222ccf48f626b27c281d5898a19211f406f92845eda0ffe3057`; S2 debt is documented by the proposal but the unchanged CI workflow spec still requires this scope |

The pre-commit run produced no worktree side effects. `git diff --check` is clean. No migration path changed in `d826654..9938429`.

### Spec compliance matrix

| Requirement | Scenario | Covering test / evidence | Result |
|---|---|---|---|
| CACHE-1 | Guild cache isolation | `tests/test_cache.py::test_guild_isolation` | COMPLIANT |
| CACHE-1 | TTL expiry | `tests/test_cache.py::test_ttl_expiry_evicts_on_read` | COMPLIANT |
| CACHE-1 | TTL contract is documented | `tests/test_cache.py::test_default_ttl_is_300`; `tests/test_pr3_inventory.py::test_schema_inventory_cdc_and_ttl_documented` verify values, not the complete deferral wording | PARTIAL |
| CACHE-1 | Leaderboard staleness is accepted | `tests/test_economy_service.py::test_get_leaderboard_xp_cache_hit` verifies a hit, not the 30-second boundary | PARTIAL |
| CACHE-1 | Member and economy Realtime work is deferred | Proposal/spec/design text only; no runtime scenario test | UNTESTED |
| REALTIME-1 | Published table scope is explicit | `tests/test_realtime.py::TestSubscriberStart::test_start_subscribes_to_four_tables` | COMPLIANT |
| REALTIME-1 | Member and economy changes remain a documented deferral | Proposal/spec/design text only; no runtime scenario test | UNTESTED |
| REALTIME-1 | Existing CDC behavior is preserved | `tests/test_realtime.py::TestCdcDispatch::test_dispatch_invalidates_correct_guild`, DELETE, and ticket-note tests | COMPLIANT |
| QA-1 | Lint failure blocks CI | CI command is static and Ruff passes; no injected-violation runtime test | UNTESTED |
| QA-1 | Type error blocks CI | Blocking `mypy bot/` command is present and passes; no injected-failure runtime test | PARTIAL |
| QA-1 | Security issue blocks CI | Bandit command is present and passes; no injected-finding runtime test | UNTESTED |
| QA-1 | Coverage below gate blocks CI | `tests/test_ci_config.py::TestCICoverageGate::test_pytest_has_cov_fail_under_75` checks configuration, not a below-threshold run | PARTIAL |
| QA-1 | Current baseline suite remains accepted | `uv run pytest -q`: 1814 passed, 3 skipped, 88.61% | COMPLIANT |
| CI-1 | Full source scope is checked | `.github/workflows/ci.yml` checks full Ruff/bot-tests scopes but runs `mypy ... bot/`; `ci-workflow-file/spec.md` requires `mypy bot tests` | FAILING |
| CI-1 | Curated-list drift cannot pass | Ruff and format cover `bot/ tests/`, but the required workflow mypy scope omits tests | FAILING |
| CI-1 | Baseline verification remains green | Full local Ruff/format/Bandit/pytest and `mypy bot/` pass; required `mypy bot tests` exits 1 with 28 errors | FAILING |
| DB-1 | Service-role startup validation succeeds | `tests/test_pr3_service_role_rls.py::TestServiceRoleConnect::test_service_role_connect_succeeds_with_valid_key` passes with an unsigned fake JWT; cryptographic verification is not proven | PARTIAL |
| DB-1 | Non-service startup fails closed | An isolated production probe rejects `test-key` and anon, but accepts an unsigned JWT whose payload claims `service_role` | FAILING |
| DB-1 | Negative non-service access test | `tests/test_pr3_service_role_rls.py::TestRlsAnonDenied::test_rls_anon_denied_on_9_tables` tests a helper, not a real table read | PARTIAL |
| DB-1 | Advisor findings do not authorize repair | `tests/test_ticket_integrity.py::test_advisor_findings_do_not_authorize_repair` | COMPLIANT |
| DB-2 | Inventory records matching state | `tests/test_ticket_integrity.py::test_runtime_parity_binder_joins_disk_registry_and_schema` passes supplied facts; `SchemaInventory.build()` supplies empty/unknown live facts and only records deferral | PARTIAL |
| DB-2 | Drift blocks schema work | `tests/test_ticket_integrity.py::test_runtime_parity_binder_rejects_mismatched_disk_bytes` proves binder failure, not live FK/RLS inventory-driven DDL blocking | PARTIAL |
| DB-3 | Cross-guild access is denied | `tests/test_pr3_inventory.py::test_guild_scope_cross_guild_detection` only detects `get_ticket` as a gap; current ID-only DB methods remain unscoped | FAILING |
| DB-3 | Unscoped path is reported | `tests/test_pr3_inventory.py::test_guild_scope_gaps_enumerates_id_only_methods`; `test_guild_scope_cross_guild_detection` | COMPLIANT |
| PRE-1 | Ruff check runs first | `tests/test_precommit_config.py::TestPrecommitHookOrder::test_ruff_before_ruff_format` | COMPLIANT |
| PRE-1 | Hooks scope to bot and tests directories | `tests/test_precommit_config.py::TestPrecommitFilesPattern::test_ruff_check_files_pattern` and `test_ruff_format_files_pattern` | COMPLIANT |
| PRE-1 | Non-target files are skipped | Regex is configured; no runtime non-target invocation test | PARTIAL |
| PRE-1 | Ruff revision is reproducible | `.pre-commit-config.yaml` pins `v0.15.20`; `uv run ruff --version` reports 0.15.20; no isolated environment-install test | PARTIAL |
| PRE-2 | Baseline all-files run passes | `uv run --with pre-commit pre-commit run --all-files`: every hook passed | COMPLIANT |
| PRE-2 | A hook failure blocks the gate | Pre-commit is blocking by default, but no injected-finding runtime test was run | PARTIAL |
| RUFF-1 | Ruff reads config from pyproject.toml | `tests/test_ruff_config.py` plus passing `uv run ruff check bot/ tests/` | COMPLIANT |
| RUFF-1 | New rule groups are enforced | `tests/test_ruff_config.py::TestRuffSelectGroups::test_select_includes_new_group` parameterization plus passing Ruff execution | COMPLIANT |
| RUFF-1 | Ruff version is aligned | `pyproject.toml`, pinned `uv.lock`/pre-commit revision, and `uv run ruff --version` | COMPLIANT |
| RUFF-1 | McCabe complexity limit is enforced | `tests/test_ruff_config.py::TestRuffMcCabe::test_max_complexity_is_15`; no >15 fixture | PARTIAL |
| RUFF-1 | Test files retain S101/ARG/T20 exceptions | `tests/test_ruff_config.py::TestRuffTestIgnores` plus passing Ruff execution | COMPLIANT |
| RUFF-1 | Ratcheted production configuration is clean | `pyproject.toml` has explicit `TRY003/TRY004/TRY300/TRY301`, no broad production `TRY`, and Ruff exits 0 | COMPLIANT |
| MYPY-1 | Strict mode is enabled | `tests/test_mypy_config.py::TestMypyStrict::test_strict_is_true`; `uv run mypy bot/` | COMPLIANT |
| MYPY-1 | Only tech-debt overrides remain | `tests/test_mypy_config.py::TestMypyOverrides::test_only_tech_debt_overrides_remain` | COMPLIANT |
| MYPY-1 | bot.core passes strict without suppression | `uv run mypy bot/`; no `bot.core.*` override | COMPLIANT |
| MYPY-1 | bot.listeners passes strict without suppression | `uv run mypy bot/`; no `bot.listeners.*` override | COMPLIANT |
| MYPY-1 | bot.bot passes strict without suppression | `uv run mypy bot/`; no `bot.bot` override | COMPLIANT |
| MYPY-1 | bot.models has no type-arg suppression | `tests/test_mypy_config.py::TestMypyNoModelsWildcard::test_no_models_wildcard_override`; `uv run mypy bot/` | COMPLIANT |
| MYPY-1 | Callbacks use the concrete bot context | `bot/cogs/tickets.py` and `bot/cogs/setup.py` now use `NebulosaContext`, but `utility.py` and `sentinel.py` still use `Context[Any]` with a cog-wide arg-type override | PARTIAL |
| MYPY-1 | Full bot and test gate is clean under the updated S1 scope | Updated spec/proposal require `mypy bot/`; it passes. `mypy bot/ tests/` remains a documented S2 debt outside that revised scope | COMPLIANT |

**Compliance summary**: 22/44 scenarios fully compliant; 13 partial; 4 untested; 5 failing. **Requirement completion** (all scenarios compliant): 0/11.

### Correctness (static and runtime evidence)

| Area | Status | Notes |
|---|---|---|
| Per-guild cache and TTL constants | Implemented | Guild keys are centralized; 300-second default and 30-second leaderboard constants are present and tested. |
| Four-table CDC invalidation | Implemented | Subscriber registers exactly `guild`, `greeting_config`, `ticket`, and `ticket_note`; CDC invalidation tests pass. |
| Pre-commit gate | Implemented | All-files run passes after the remediation; GGA now executes through `bash .gga`. |
| Ruff ratchet | Implemented | Broad production `TRY` was replaced with explicit residual codes; Ruff passes. |
| Mypy bot scope | Implemented | `mypy bot/` passes; test debt remains 28 errors and is explicitly deferred by the updated proposal/QA spec. |
| Service-role startup gate | Not fully implemented | Test sentinel is rejected outside test environments, but an unsigned service-role-claiming JWT is accepted. |
| Schema/FK/RLS/015 inventory | Partial | Runtime parity binder exists and fails closed for supplied mismatches, but `SchemaInventory.build()` does not obtain or compare live FK/RLS facts. |
| Guild ownership boundary | Not implemented for inventoried gaps | The gap registry and detection test exist; ID-only database methods still do not establish ownership. |
| CI workflow contract | Inconsistent | Workflow uses `mypy bot/`, while the unchanged `ci-workflow-file` requirement still mandates `mypy bot tests`. |
| No DDL | Verified | No migration file changed; inventory emits empty DDL and `no_ddl=True`. |
| Review budget | Partial | Remediation is 264 changed lines, but the documented PR2 sequential value is 616, which exceeds 600. |

### Design coherence

| Decision | Followed? | Notes |
|---|---|---|
| Five bottom-up slices | Yes | The stacked chain and remediation commit are present. |
| Explicit residual Ruff codes | Yes | Production ignores list explicit `TRY` residuals. |
| Parameterized context | Partial | Tickets/setup migrated; utility/sentinel remain on `Context[Any]` under the documented hybrid-stub override. |
| Server-only service-role access | No | Startup rejects common non-service roles but does not verify JWT signatures. |
| Read-only schema/FK/015 inventory | Partial | No DDL and 015/runtime binder are present; live FK/RLS matching is deferred rather than inventoried. |
| Cache-first plus four-table CDC | Yes | Existing service/cache paths and CDC behavior remain green. |
| Revertable stacked slices | Yes | Remediation is a single 264-line delta; no migration changes. |
| Sequential review budget | No | Proposal claims PR2 is 616 while also claiming every slice is <=600. |
| S2 deferrals | Partial | Proposal/QA specs document test mypy and live FK/RLS deferrals, but database and CI-workflow specs are not fully aligned with those deferrals. |

### TDD compliance

| Check | Result | Details |
|---|---|---|
| TDD evidence reported | PASS | `apply-progress.md` contains five original TDD tables and a remediation TDD section. |
| All implementation tasks complete | PASS | Native status reports 19/19 checkboxes complete. |
| RED test files exist | PARTIAL | Changed focused files exist and pass, but the remediation's unsigned-JWT/test-key production claim has no covering regression test. |
| GREEN tests pass | PASS | Full suite and 96 focused tests pass. |
| Triangulation adequate | WARNING | Schema/guild remediation tests assert inventory facts, not live access isolation or live FK/RLS matching. |
| Safety nets recorded | PASS | Apply evidence records regression gates for implementation slices. |

**TDD Compliance**: 4/6 checks fully passed; triangulation is a warning.

### Test layer distribution

| Layer | Tests | Files | Tools |
|---|---:|---:|---|
| Unit / structural | 526 test functions across 25 changed test files (parameterized collection expands this count) | 25 | pytest + pytest-asyncio |
| Integration | 0 | 0 | Not configured for this change |
| E2E | 0 | 0 | Not configured (`e2e: false`) |
| **Total** | **526 functions** | **25** | |

### Changed-file coverage

Coverage from the full suite: 5,101/5,757 statements, 88.61%; branch coverage is not configured.

| File | Line % | Uncovered lines | Rating |
|---|---:|---|---|
| `bot/cogs/core.py` | 85.48% | 112,123,182-188,196,198-200,202-203,232-234,251,256 | Acceptable |
| `bot/cogs/greetings.py` | 92.42% | 66-67,81-82,304,330,372,432,458,500,518,524,528-530 | Acceptable |
| `bot/cogs/ocio.py` | 97.56% | 113 | Excellent |
| `bot/cogs/setup.py` | 76.47% | 76,82,89-91,97,110-112,118,141,146 | Low |
| `bot/cogs/stellar.py` | 95.54% | 272-274,299,304 | Excellent |
| `bot/cogs/tickets.py` | 82.55% | 107-112,126-128,133-138,184-185,226-232,259,269-272,278-281,295,301-304,343,348-351,361-364,370-373,447-450,508-509,548-551,561-565,602-604,642,647,657-660,701-704,723-725,733,780,818-822,894-895,934-935,974-977,1056-1059,1075,1079 | Acceptable |
| `bot/config.py` | 90.91% | 24,29-30,39,57,64 | Acceptable |
| `bot/core/cache.py` | 100.00% | - | Excellent |
| `bot/core/context.py` | 78.57% | 44,49,58 | Low |
| `bot/core/db/base.py` | 97.56% | 42 | Excellent |
| `bot/core/db/economy_db.py` | 91.55% | 41,79,118,159,181,209 | Acceptable |
| `bot/core/db/guild_db.py` | 85.29% | 47,57-58,60-61 | Acceptable |
| `bot/core/db/member_db.py` | 100.00% | - | Excellent |
| `bot/core/i18n.py` | 95.24% | 74-75,167,173 | Excellent |
| `bot/services/economy_service.py` | 98.57% | 226,344 | Excellent |
| `bot/services/greeting_service.py` | 90.23% | 129,135,230-231,292-294,301-303,311-313 | Acceptable |
| `bot/services/guild_service.py` | 92.68% | 127,185,187,217-219 | Acceptable |
| `bot/services/image_service.py` | 94.54% | 144-148,424-425,429,447-448 | Excellent |
| `bot/services/logging_service.py` | 92.95% | 228,289,316,341,366,385,396,413,452,472-473 | Acceptable |
| `bot/services/schema_inventory.py` | 90.57% | 86,141-142,158-159 | Acceptable |
| `bot/services/ticket_field_service.py` | 98.70% | 125 | Excellent |
| `bot/utils/checks.py` | 93.75% | 43-44,46-47,49 | Acceptable |
| `bot/utils/ticket_helpers.py` | 90.35% | 223,254-256,263,278-280,287,289,296 | Acceptable |

**Average changed-file coverage**: 90.83% across these 24 changed `bot/` Python files; two files are below 80% (`setup.py`, `context.py`).

### Assertion quality

No tautologies, ghost loops, or assertions that avoid production/configuration calls were found in the remediation tests. The `hasattr` checks in `test_pr3_inventory.py` are paired with concrete value assertions. Mocked tests remain unit-level by design.

### Issues found

**CRITICAL**

1. **CI-1 is still contradictory.** `openspec/changes/cleanup-stability/specs/ci-workflow-file/spec.md` still requires `mypy bot tests`, while `.github/workflows/ci.yml` runs `mypy ... bot/`. The full command exits 1 with 28 errors, so all three CI-1 scenarios remain failing under the authoritative 11/44 specs.
2. **DB-1 is not fully fail-closed.** `bot/config.py::_decode_jwt_role()` accepts a JWT solely from its decoded role claim. With `PYTEST_CURRENT_TEST` unset and `ENV=production`, an unsigned `service_role` JWT with `fake-signature` was accepted. The prior remediation only closes the `test-key` sentinel path.
3. **DB-2 still lacks live FK/RLS inventory.** `SchemaInventory.build()` invokes `bind_runtime_parity` with `live_migration_ids=[]` and unknown live schema facts, then returns `fk_live_verified=False` and `rls_live_verified=False`. This records a deferral but does not satisfy the database spec's live/disk matching contract.
4. **DB-3 still exposes inventoried ownership gaps.** `ticket_db.update_ticket()` filters only by ticket ID, and category/note ID-only operations do the same. The new test proves that `get_ticket` is listed as a gap; it does not prove that a guild-A request rejects guild-B data.
5. **The sequential budget claim remains over limit.** The remediation commit is 264 changed lines, but the updated proposal/apply evidence still records PR2 as 616 authored lines while claiming every sequential slice is <=600. The original cumulative-diff issue was reworded, not numerically resolved.

**WARNING**

1. Mypy context migration is only partial under the literal callback requirement: `tickets.py` and `setup.py` are fixed, while `utility.py` and `sentinel.py` retain `Context[Any]` and rely on the cog override. The updated artifacts document this as hybrid-stub debt, so it is not counted as an additional blocker.
2. The RLS negative scenario calls `is_rls_denied_for_anon()` rather than a real Supabase table read; no live credentials or integration layer is configured.
3. CI/pre-commit failure-injection scenarios, cache leaderboard expiry, and explicit member/economy deferral behavior lack runtime covering tests.
4. `apply-progress.md` says 17/17 tasks in its status text while native status and `tasks.md` report 19/19; `openspec/config.yaml` says 1812 tests while the current suite has 1814.
5. Changed-file coverage is low for `bot/cogs/setup.py` (76.47%) and `bot/core/context.py` (78.57%); coverage is informational, not a gate failure.
6. All change-specific tests are unit/structural; no integration or E2E layer exercises the real Supabase, CI, or Discord boundaries.

**SUGGESTION**

1. Align `ci-workflow-file/spec.md` with the accepted S1 `mypy bot/` deferral, or remove the deferral and clear the 28 test errors before claiming a green full-scope workflow.
2. Add regression coverage for unsigned JWT rejection, live-inventory mismatch handling, and an actual cross-guild negative DB query.
3. Replace the literal 616 PR2 budget entry with a truthful exception or a measured <=600 sequential delta.

### Verdict

**FAIL** - 5 critical blockers remain despite green local pytest, Ruff, bot-only mypy, py_compile, Bandit, and pre-commit gates.
