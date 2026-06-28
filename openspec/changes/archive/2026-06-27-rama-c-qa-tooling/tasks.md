# Tasks: rama-c-qa-tooling

Generated from proposal + design + 11 specs.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1350 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 |
| Delivery strategy | force-chained |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | PR | Notes |
|------|------|----|-------|
| 1 | Bootstrap QA tooling: pyproject, pre-commit, Makefile, CI, frozen_clock, property scaffold | PR 1 | Base = tracker branch `rama-c-qa-tooling`; ~250 lines; gate 55% |
| 2 | Coverage #1: config + database unit tests | PR 2 | Base = PR 1 branch; ~400 lines; gate 60% |
| 3 | Coverage #2: integration flows, cog coverage, property battery | PR 3 | Base = PR 2 branch; ~700 lines; gate 70% |

---

## PR 1 — Bootstrap (target ~250 lines; coverage gate 55%)

### Task 1.1 — Update pyproject.toml with QA tool configs

- **Traceability**: design.md Section "pyproject.toml Delta"; `pyproject-toml-qa-config/spec.md`
- **Acceptance criteria**:
  - `[tool.ruff]` block present with `target-version = "py311"`, `line-length = 120`, lint select rules `[E,W,F,I,N,UP,B,SIM,RUF]`, isort `known-first-party = ["bot"]`
  - `[tool.mypy]` block present with `python_version = "3.11"`, `strict_optional = true`, `warn_unused_ignores = true`, `disable_error_code = "attr-defined"`
  - `[[tool.mypy.overrides]]` for `module = "bot.bot"` with `disable_error_code = ["attr-defined"]`
  - `[tool.bandit]` with `exclude_dirs = ["tests", "dashboard"]`
  - `[tool.pytest.ini_options]` with `asyncio_mode = "auto"`, `testpaths = ["tests"]`, `addopts = "--cov=bot --cov-fail-under=55 --randomly-seed=42"`
  - `filterwarnings` list with 3 entries (discord.py coroutine deprecation, asyncio.iscoroutinefunction deprecation, hypothesis deprecation)
  - `[project.optional-dependencies.dev]` listing: `pytest`, `pytest-asyncio`, `pytest-cov`, `pytest-randomly`, `hypothesis`, `freezegun`, `ruff`, `mypy`, `bandit`
  - `pyproject.toml` parses without error (`python -c "import tomllib; tomllib.load(open('pyproject.toml','rb'))"`)
  - `pytest --co -q` succeeds with new addopts (257/257 collected)
- **Dependencies**: none.

### Task 1.2 — Add frozen_clock fixture to tests/conftest.py

- **Traceability**: design.md Section "tests/conftest.py Extension — frozen_clock"; `conftest-frozen-clock/spec.md`
- **Acceptance criteria**:
  - `_FROZEN_NOW = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)` constant defined
  - `frozen_clock` fixture using `freezegun.freeze_time(_FROZEN_NOW)` context manager, yields `_FROZEN_NOW`
  - `from freezegun import freeze_time` import present
  - `pytest --co -q` succeeds; fixture is importable from any test module
- **Dependencies**: Task 1.1 (freezegun must be in dev deps).

### Task 1.3 — Migrate existing datetime-dependent tests to frozen_clock

- **Traceability**: design.md Section "tests/conftest.py Extension — frozen_clock"; `conftest-frozen-clock/spec.md` (Requirement: Tests using datetime.now MUST opt in)
- **Acceptance criteria**:
  - `tests/test_economy_service.py` — all 9 `datetime.now(timezone.utc)` call sites (lines 209, 232, 259, 351, 357, 388, 389, 415, 441) replaced with `frozen_clock` fixture consumption
  - Each migrated test declares `frozen_clock` in its function signature
  - `grep -n 'datetime.now' tests/test_economy_service.py` returns 0 matches
  - `pytest tests/test_economy_service.py -q` passes 100%
  - `pytest --randomly-seed=0 tests/test_economy_service.py -q` passes (random order determinism)
- **Dependencies**: Task 1.2.

### Task 1.4 — Create .pre-commit-config.yaml

- **Traceability**: design.md Section ".pre-commit-config.yaml Content"; `pre-commit-config-file/spec.md`; `qa-pre-commit/spec.md`
- **Acceptance criteria**:
  - File matches design.md snapshot exactly: 4 repos (pre-commit-hooks v5.0.0, astral-sh/ruff-pre-commit v0.8.6, pre-commit/mirrors-mypy v1.13.0, local)
  - Hook order: trailing-whitespace → end-of-file-fixer → check-yaml → check-added-large-files → ruff (--fix) → ruff-format (--check) → mypy (--config-file=pyproject.toml, pass_filenames=false, entry=mypy bot/) → bandit (language=system) → gga (language=script, always_run=true)
  - mypy hook `additional_dependencies` includes `discord.py-stubs` and `types-PyYAML`
  - `pre-commit run --all-files` executes each hook in listed order
  - `SKIP=gga pre-commit run --all-files` bypasses the GGA hook cleanly
- **Dependencies**: Task 1.1 (pyproject.toml must have mypy/ruff config for hooks to read).

### Task 1.5 — Create Makefile

- **Traceability**: design.md Section "Makefile Content"; `makefile-dx/spec.md`
- **Acceptance criteria**:
  - `.PHONY: lint type security test cov ci audit` declared
  - `lint` target runs `ruff check bot/` then `ruff format --check bot/`
  - `type` target runs `mypy bot/`
  - `security` target runs `bandit -r bot/ -c pyproject.toml`
  - `test` target runs `pytest`
  - `cov` target runs `pytest --cov=bot --cov-report=term --cov-report=html`
  - `ci` target depends on `lint type security test cov` (runs in order, fails fast)
  - `audit` target runs `uv run --with pip-audit pip-audit --strict`
  - `make lint` succeeds on clean code; `make ci` runs full chain
- **Dependencies**: Task 1.1 (tools must be configured).

### Task 1.6 — Verify GGA shell hook integration with pre-commit

- **Traceability**: design.md Section ".pre-commit-config.yaml Content"; `pre-commit-config-file/spec.md` (GGA shell hook as script entry); `qa-pre-commit/spec.md`
- **Acceptance criteria**:
  - `.gga` file has executable bit set (`test -x .gga`)
  - `pre-commit run gga --all-files` exits 0 on conformed code
  - `pre-commit run gga --all-files` exits non-zero when a deliberate AGENTS.md violation is introduced (test with a known bad pattern)
  - `SKIP=gga pre-commit run --all-files` skips GGA without error
- **Dependencies**: Task 1.4.

### Task 1.7 — Create .github/workflows/ci.yml

- **Traceability**: design.md Section ".github/workflows/ci.yml Structure"; `ci-workflow-file/spec.md`; `qa-ci-pipeline/spec.md`
- **Acceptance criteria**:
  - Workflow triggers on `push` (all branches), `pull_request` (master), `schedule` (cron)
  - `permissions: contents: read` set
  - `concurrency: group: ci-${{ github.ref }}, cancel-in-progress: true` set
  - `env: PYTHONASYNCIODEBUG: "1"` set at workflow level
  - `qa-matrix` job: `ubuntu-latest`, strategy matrix `["3.11", "3.12", "3.14"]`, `fail-fast: false`
  - Steps: checkout@v4 → setup-python@v5 → cache uv (actions/cache@v4 with `uv-${{ runner.os }}-${{ matrix.python-version }}-${{ hashFiles('uv.lock') }}` key) → `pip install uv && uv sync --dev` → ruff check → ruff format --check → mypy → bandit → `uv run --with pip-audit pip-audit --strict` → pytest → upload-artifact (coverage on 3.12 only)
  - `pip-audit-weekly` job: `ubuntu-latest`, `if: github.event_name == 'schedule'`, Python 3.12, runs pip-audit only
  - YAML is syntactically valid (`python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`)
- **Dependencies**: Task 1.1 (pyproject.toml must have tool configs for CI steps to read).

### Task 1.8 — Verify weekly pip-audit schedule job isolation

- **Traceability**: `ci-workflow-file/spec.md` (Scenario: Weekly schedule triggers audit); `qa-ci-pipeline/spec.md` (Requirement: pip-audit on push and weekly schedule)
- **Acceptance criteria**:
  - `pip-audit-weekly` job has `if: github.event_name == 'schedule'` guard
  - `qa-matrix` job runs on push/PR (no schedule guard)
  - Both jobs are independent (no `needs:` dependency between them)
  - Workflow YAML parses cleanly
- **Dependencies**: Task 1.7.

### Task 1.9 — Scaffold property test directory with smoke tests

- **Traceability**: design.md Section "Hypothesis Property Test Pattern"; `qa-property-tests/spec.md`
- **Acceptance criteria**:
  - `tests/property/__init__.py` exists (empty package marker)
  - `tests/property/test_economy_math_smoke.py` contains 2-3 hypothesis tests:
    - `test_compute_xp_for_level_zero_returns_base`: `compute_xp_for_level(0, ...) == 0`
    - `test_compute_xp_for_level_positive`: non-negativity property for any valid level
    - `test_compute_level_non_negative`: non-negativity property for any valid XP
  - Strategies bounded: `level_strategy = st.integers(min_value=0, max_value=1000)`, `xp_strategy = st.integers(min_value=0, max_value=10_000_000)`
  - `@settings(max_examples=50, deadline=None)` on each test
  - `pytest tests/property/test_economy_math_smoke.py -q` passes
  - `pytest --co -q` discovers tests in `tests/property/` subdirectory
- **Dependencies**: Task 1.1 (hypothesis must be in dev deps).

### Task 1.10 — Update .gitignore for QA tooling artifacts

- **Traceability**: `pyproject-toml-qa-config/spec.md` (coverage gate ratchet implies coverage artifacts)
- **Acceptance criteria**:
  - `.coverage` entry present in `.gitignore`
  - `.pytest_cache/` entry present
  - `htmlcov/**` entry present
  - `.venv/**` entry present (if not already)
  - `git status` does not show `.coverage` or `.pytest_cache/` as untracked after a pytest run
- **Dependencies**: none.

---

## PR 2 — Coverage #1 (target ~400 lines; coverage gate 60%)

### Task 2.1 — Raise coverage gate to 60% in pyproject.toml

- **Traceability**: design.md Section "pyproject.toml Delta" (Gate ratchet plan); `pyproject-toml-qa-config/spec.md` (Requirement: Coverage gate ratchet)
- **Acceptance criteria**:
  - `addopts` line changed to `"--cov=bot --cov-fail-under=60 --randomly-seed=42"`
  - `grep 'cov-fail-under' pyproject.toml` shows `60`
- **Dependencies**: Task 1.1.

### Task 2.2 — Implement tests/test_config.py for bot/config.py

- **Traceability**: `qa-config-coverage/spec.md` (Requirement: Config module reaches 80% coverage); design.md Section "Architecture Decisions"
- **Acceptance criteria**:
  - Tests cover `BotConfig` dataclass fields and `BotConfig.from_env()` classmethod
  - Scenario: default config values applied when env vars missing
  - Scenario: custom config values override defaults when env vars set
  - Scenario: invalid/missing fields fall back to defaults without exception
  - `pytest tests/test_config.py -q` passes
  - `pytest --cov=bot/config.py --cov-report=term-missing tests/test_config.py` shows ≥80% coverage on `bot/config.py`
- **Dependencies**: Task 1.1.

### Task 2.3 — Implement tests/test_database.py: core CRUD + guild methods

- **Traceability**: `qa-database-coverage/spec.md` (Requirement: Database module reaches 45% coverage); design.md Section "Architecture Decisions"
- **Acceptance criteria**:
  - Uses `AsyncMock(spec=Database)` pattern — no real Supabase connection
  - Tests cover these public methods:
    - `connect` — happy path + failure
    - `health_check` — returns True/False
    - `get_guild` — found + not-found (returns None)
    - `upsert_guild` — idempotent upsert
    - `get_member` — found + not-found
    - `get_infractions` — returns list for guild
    - `get_active_warnings` — returns filtered list
    - `insert_ticket` — creates ticket record
    - `get_ticket` / `get_ticket_by_channel` — found + not-found
  - Scenario: guild-scoped query filters correctly (assert guild_id passed to Supabase client)
  - Scenario: missing record returns None without exception
  - `pytest tests/test_database.py -q` passes
- **Dependencies**: Task 1.1.

### Task 2.4 — Implement tests/test_database.py: economy + leaderboard methods

- **Traceability**: `qa-database-coverage/spec.md` (Requirement: Database module reaches 45% coverage); design.md Section "Architecture Decisions"
- **Acceptance criteria**:
  - Tests added to `tests/test_database.py` (same file, continued from 2.3):
    - `update_member_xp` — increments XP correctly
    - `update_member_coins` — increments coins correctly
    - `update_member_daily` — updates streak + last_daily_reset
    - `get_economy_config` — found + not-found
    - `upsert_economy_config` — idempotent upsert
    - `get_leaderboard` — returns ordered list with correct limit
    - `get_member_rank` — returns correct rank position
    - `get_greeting_config` — found + not-found
  - Scenario: upsert is idempotent (same data → no duplicate)
  - `pytest tests/test_database.py -q` passes (all tests from 2.3 + 2.4)
  - `pytest --cov=bot/core/database.py --cov-report=term-missing tests/test_database.py` shows ≥45% coverage
- **Dependencies**: Task 2.3.

### Task 2.5 — Prepare PR2 branch off PR1 commit

- **Traceability**: proposal.md (PR2 — Coverage #1); chained-pr skill (Feature Branch Chain rules)
- **Acceptance criteria**:
  - Branch created from PR1's merge commit (or PR1 branch head if not yet merged)
  - `git diff PR1_HEAD..HEAD --stat` shows only: `pyproject.toml` (addopts change) + `tests/test_config.py` + `tests/test_database.py`
  - No unrelated files modified
  - **Dependencies**: Tasks 2.1, 2.2, 2.3, 2.4.

---

## PR 3 — Coverage #2 + Integration (target ~700 lines; coverage gate 70%)

### Task 3.1 — Raise coverage gate to 70% in pyproject.toml

- **Traceability**: design.md Section "pyproject.toml Delta" (Gate ratchet plan); `pyproject-toml-qa-config/spec.md`
- **Acceptance criteria**:
  - `addopts` line changed to `"--cov=bot --cov-fail-under=70 --randomly-seed=42"`
  - `grep 'cov-fail-under' pyproject.toml` shows `70`
- **Dependencies**: Task 2.1.

### Task 3.2 — Create tests/integration/__init__.py

- **Traceability**: design.md Section "Test File Naming & Directory Layout"
- **Acceptance criteria**:
  - Empty `__init__.py` in `tests/integration/`
  - `pytest --co -q tests/integration/` discovers integration tests (once they exist)
- **Dependencies**: none.

### Task 3.3 — Implement tests/integration/test_moderation_flow.py

- **Traceability**: `qa-integration-flows/spec.md` (Requirement: Moderation warn round-trip); design.md Section "Integration Test Pattern"
- **Acceptance criteria**:
  - `TestModerationFlow` class with tests:
    - `test_warn_persists_infraction_and_sends_log_embed` — moderator with `moderate_members` issues `/warn` with reason → assert `mock_db.insert_infraction` called with correct guild_id, user_id, action="warn", reason → assert log embed sent with moderator, target, action type, reason
    - `test_warn_without_log_channel_skips_embed` — `logChannelId` not configured → infraction persisted, no embed attempted
  - Uses existing conftest mocks (`mock_db`, `mock_interaction`, `cache`) — no new test infrastructure
  - Wires `InfractionService` + `GuildService` + `LoggingService` → `SentinelCog`
  - `pytest tests/integration/test_moderation_flow.py -q` passes
- **Dependencies**: Task 3.2.

### Task 3.4 — Implement tests/integration/test_ticket_flow.py

- **Traceability**: `qa-integration-flows/spec.md` (Requirement: Ticket lifecycle round-trip); design.md Section "Integration Test Pattern"
- **Acceptance criteria**:
  - `TestTicketFlow` class with tests:
    - `test_open_ticket_creates_channel_with_correct_permissions` — panel button click → `guild.create_text_channel` called → permission overwrites assert user can send, @everyone cannot see
    - `test_close_ticket_generates_transcript` — close button → transcript generated → channel scheduled for deletion
  - Mocks `guild.create_text_channel`, `interaction.response`, transcript service
  - `pytest tests/integration/test_ticket_flow.py -q` passes
- **Dependencies**: Task 3.2.

### Task 3.5 — Implement tests/integration/test_xp_flow.py

- **Traceability**: `qa-integration-flows/spec.md` (Requirement: XP message-to-level-up flow); design.md Section "Integration Test Pattern"
- **Acceptance criteria**:
  - `TestXpFlow` class with tests:
    - `test_message_accumulation_triggers_level_up` — member with 0 XP sends enough messages to cross threshold → assert level increments by 1 → assert level-up notification sent
    - `test_xp_cooldown_prevents_spam` — member who just gained XP sends another message within cooldown → no additional XP awarded
  - Uses `frozen_clock` fixture for deterministic datetime
  - Calls `EconomyService.gain_xp()` 10+ times, asserts `update_member_xp` args + level-up embed
  - `pytest tests/integration/test_xp_flow.py -q` passes
- **Dependencies**: Tasks 3.2, 1.2 (frozen_clock).

### Task 3.6 — Create tests/test_sentinel_cog.py: scaffold + warn/unwarn commands

- **Traceability**: proposal.md (PR3 — sentinel 28% → 60%); `qa-integration-flows/spec.md` (moderation flow); design.md Section "Integration Test Pattern"
- **Acceptance criteria**:
  - New file `tests/test_sentinel_cog.py`
  - Test scaffolding: `SentinelCog` instantiated with mocked bot, mocked `InfractionService`, mocked `GuildService`, mocked `LoggingService`
  - `test_warn_persists_infraction_and_sends_log_embed` — mock interaction with `moderate_members` perm → call `warn` → assert `insert_infraction` args + response embed
  - `test_unwarn_deactivates_infraction` — mock interaction → call `unwarn` → assert `deactivate_infraction` called + response embed
  - `pytest tests/test_sentinel_cog.py -q` passes
- **Dependencies**: Task 1.1.

### Task 3.7 — Extend tests/test_sentinel_cog.py: mute/unmute/kick/ban commands

- **Traceability**: proposal.md (PR3 — sentinel 28% → 60%); `qa-integration-flows/spec.md`
- **Acceptance criteria**:
  - Tests for `mute`, `unmute`, `kick`, `ban` commands added to existing test file
  - Each test: mock interaction with appropriate permissions → call command → assert DB method called + response sent
  - `test_mute_adds_timeout_and_logs` — assert member.timeout called + log embed
  - `test_unmute_removes_timeout_and_logs` — assert member.timeout(None) called
  - `test_kick_calls_guild_kick` — assert guild.kick called + log embed
  - `test_ban_calls_guild_ban` — assert guild.ban called + log embed
  - `pytest tests/test_sentinel_cog.py -q` passes (all tests from 3.6 + 3.7)
- **Dependencies**: Task 3.6.

### Task 3.8 — Extend tests/test_sentinel_cog.py: lock/unlock/modlogs + helpers

- **Traceability**: proposal.md (PR3 — sentinel 28% → 60%)
- **Acceptance criteria**:
  - Tests for `lock`, `unlock`, `modlogs` commands
  - `test_lock_sets_channel_permissions` — assert channel.set_permissions called for @everyone
  - `test_unlock_restores_channel_permissions` — assert permissions restored
  - `test_modlogs_shows_infraction_history` — assert paginated embed sent
  - `_ModlogsPaginator` tested: prev/next button navigation, embed page content update
  - `_validate_target` tested: self-target rejection returns error, higher-role target rejection returns error
  - `_handle_mod_error` tested: `discord.Forbidden` → permission error embed, `discord.HTTPException` → generic error embed
  - `pytest tests/test_sentinel_cog.py -q` passes
  - `pytest --cov=bot/cogs/sentinel.py --cov-report=term-missing tests/test_sentinel_cog.py` shows ≥60% coverage
- **Dependencies**: Task 3.7.

### Task 3.9 — Create tests/test_tickets_cog.py: panel view + open ticket

- **Traceability**: proposal.md (PR3 — tickets 15% → 55%); `qa-integration-flows/spec.md` (ticket lifecycle)
- **Acceptance criteria**:
  - New file `tests/test_tickets_cog.py`
  - `TicketPanelView.open_ticket_button` tested: mock interaction → assert channel created with correct category, support role permission overwrite, user permission overwrite
  - `test_open_ticket_sends_initial_embed` — assert first message in new channel is a ticket embed
  - `_CategorySelect` callback tested: selection triggers ticket creation in correct category
  - `pytest tests/test_tickets_cog.py -q` passes
- **Dependencies**: Task 1.1.

### Task 3.10 — Extend tests/test_tickets_cog.py: claim/close/transcript + stale auto-close

- **Traceability**: proposal.md (PR3 — tickets 15% → 55%); `qa-integration-flows/spec.md`
- **Acceptance criteria**:
  - `TicketActionsView.claim_button` tested: assert ticket claimed, interaction response sent
  - `TicketActionsView.close_button` tested: assert transcript generated, channel scheduled for deletion, transcript file sent
  - `auto_close_stale_tickets` tested: stale tickets (last activity > threshold) closed, fresh tickets untouched
  - `pytest tests/test_tickets_cog.py -q` passes (all tests from 3.9 + 3.10)
  - `pytest --cov=bot/cogs/tickets.py --cov-report=term-missing tests/test_tickets_cog.py` shows ≥55% coverage
- **Dependencies**: Task 3.9.

### Task 3.11 — Extend tests/property/test_economy_math.py with full hypothesis battery

- **Traceability**: `qa-property-tests/spec.md` (Requirements: Property tests for compute_xp_for_level, compute_level); design.md Section "Hypothesis Property Test Pattern"
- **Acceptance criteria**:
  - File `tests/property/test_economy_math.py` contains:
    - `test_compute_xp_for_level_positive` — XP threshold ≥ 0 for any level in [0, 1000]
    - `test_compute_xp_for_level_monotonic` — higher level → higher XP threshold
    - `test_compute_level_non_negative` — level ≥ 0 for any XP in [0, 10_000_000]
    - `test_compute_level_monotonic` — higher XP → equal or higher level
  - Strategies: `level_strategy [0, 1000]`, `xp_strategy [0, 10_000_000]`, `base_strategy [1, 1000]`, `multiplier_strategy [1.01, 10.0]`
  - `@settings(max_examples=200, deadline=None)` on each test
  - `test_compute_xp_for_level_monotonic` uses `assume(level_b > level_a)` to ensure strict ordering
  - `test_compute_level_monotonic` uses `assume(xp_b >= xp_a)`
  - `pytest tests/property/test_economy_math.py -q` passes (no counterexamples on 200 examples)
- **Dependencies**: Task 1.1 (hypothesis in dev deps).

### Task 3.12 — Verify suite determinism under pytest-randomly

- **Traceability**: `conftest-frozen-clock/spec.md` (Scenario: Flake detected when frozen_clock is missing); `pyproject-toml-qa-config/spec.md` (Scenario: Deterministic seed produces same order)
- **Acceptance criteria**:
  - Run `pytest --tb=no -q` 5 consecutive times
  - ALL 5 runs show identical pass count (same number of tests passed/failed)
  - No flaky tests detected (zero variation in outcomes)
  - If any flake detected: root-cause and fix before proceeding
  - **Dependencies**: All PR3 test tasks (3.3–3.11) must be complete.

### Task 3.13 — Prepare PR3 branch off PR2 commit

- **Traceability**: proposal.md (PR3 — Coverage #2 + Integration); chained-pr skill
- **Acceptance criteria**:
  - Branch created from PR2's merge commit (or PR2 branch head)
  - `git diff PR2_HEAD..HEAD --stat` shows only: `pyproject.toml` (addopts change to 70) + new integration test files + new/extended cog test files + property test file
  - No unrelated files modified
  - **Dependencies**: Tasks 3.1–3.12.

---

## Post-Merge (Optional)

### Task 4.1 — Add coverage gate ratchet documentation to README

- **Traceability**: proposal.md (Success Criteria); design.md (Gate ratchet plan)
- **Acceptance criteria**:
  - Section in README (or CONTRIBUTING.md) explaining: current gate value, how to raise it, `addopts` location, `make cov` to check locally
  - Mentions `--randomly-seed=0` for local reseeding
  - Mentions `SKIP=gga` for WIP commits
- **Dependencies**: Task 3.1 (gate at 70% is final value to document).
