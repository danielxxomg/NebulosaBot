# pyproject.toml QA Configuration Specification

## Purpose

Configure ruff, ty, pytest, and dev dependencies in `pyproject.toml` so that all QA tooling reads its config from a single source of truth and the coverage gate ratchets incrementally across PR slices.

## Requirements

### Requirement: Ruff configuration present

`pyproject.toml` MUST contain `[tool.ruff]` with `target-version = "py311"`, `line-length = 120`. Ruff MUST resolve to `0.15.20` via lock, and `[tool.ruff]` MUST pin `required-version = "0.15.20"` exactly. `select` MUST retain `E,W,F,I,N,UP,B,SIM,RUF,S,C4,C90,RET,T20,ARG,DTZ,EM,T10,TRY,RSE,FLY,PERF,FURB` and add preview `ANN`, `PYI`, `PGH003` for ty alignment. `[tool.ruff]` MUST set `explicit-preview-rules = true`, so only explicitly named preview rules fire. `select` MUST additionally include the `ASYNC`, `BLE`, `G`, and `A` families and the single rule `PT011` (PT018 and the rest of PT deferred); each added family/rule MUST reach zero findings in the tree BEFORE its selection lands (fixes precede gates). BLE001 sites that intentionally keep broad catches MUST be narrowed or carry a reasoned per-site suppression. ASYNC240 exemptions MUST be limited to narrow per-file ignores on the specific test files that simulate blocking calls. `PLC0415` MUST remain unselected and documented as advisory via a comment at the `select` list. `[tool.ruff.lint.mccabe]` MUST set `max-complexity = 15`. Test files MUST retain `S101`, `ARG`, `T20` ignores. The broad `bot/**/*.py` suppression (17 rules) MUST be removed progressively across PR4 batches A/B/C.

(Previously: no `explicit-preview-rules`, no `required-version`, no ASYNC/BLE/G/A/PT selection, and PLC0415 undocumented.)

#### Scenario: Preview rules for ty alignment enabled

- GIVEN `ANN`, `PYI`, `PGH003` are in `select` with preview
- WHEN `ruff check bot/` runs
- THEN annotation and type-ignore-comment rules are enforced

#### Scenario: Preview rules are explicit opt-in

- GIVEN `explicit-preview-rules = true`
- WHEN ruff resolves its rule set
- THEN only preview rules named in `select` are active (unnamed preview rules stay off)

#### Scenario: bot/** suppression removed progressively

- GIVEN PR4 batches A (TRY003/EM101/EM102), B (S101/S310/S311/S110), C (ARG/TRY300/FURB/C901/F841) are applied
- WHEN `ruff check bot/` runs after all batches
- THEN zero findings are reported

#### Scenario: Test files retain exceptions

- GIVEN `tests/**/*.py` ignores include `S101`, `ARG`, `T20`
- WHEN `ruff check tests/` runs
- THEN test assertions and prints do not trigger violations

#### Scenario: Ruff reads config from pyproject.toml

- GIVEN `[tool.ruff]` is defined in `pyproject.toml`
- WHEN `ruff check` is invoked without explicit config flags
- THEN ruff reads its configuration from `pyproject.toml`

#### Scenario: McCabe complexity limit enforced

- GIVEN `[tool.ruff.mccabe]` sets `max-complexity = 15`
- WHEN a function has cyclomatic complexity above 15
- THEN ruff reports a `C901` violation

#### Scenario: New family gates are blocking at zero findings

- GIVEN ASYNC/BLE/G/A/PT011 selections have landed after their fixes
- WHEN `ruff check bot/ tests/` runs
- THEN it reports zero findings for those families and any new hit fails the check

#### Scenario: Ruff version pinned exactly

- GIVEN `required-version = "0.15.20"` is configured
- WHEN ruff is invoked under any other version
- THEN it refuses to run (version mismatch error)

### Requirement: ty configuration present

`pyproject.toml` MUST contain `[tool.ty]`. `[tool.ty.environment]` MUST set `python-version = "3.11"`. Baseline `[tool.ty.rules]` MUST apply Astral's strict ruleset. `[[tool.ty.overrides]] include = ["bot/cogs/**"]` MUST set `untyped-decorator-call` and `possibly-unresolved-import` to `warn` (discord.py stub gaps), narrowed from blanket cog/test coverage toward per-file entries per scope before warning-gating activates. `bot/` and `tests/` MUST be `error`-blocking outside cog overrides. Inline suppression MUST use `# ty: ignore[<rule>]`. `[tool.ty.terminal]` MUST set `error-on-warning = true`, making every warn-class diagnostic fatal; this gate MUST be enabled LAST — known live warnings fixed first (e.g. `invalid-argument-type` in the ticket integrity flow) and blanket overrides narrowed beforehand.

(Previously: warnings were non-fatal; blanket `bot/cogs/**` and `tests/**` overrides were tolerated.)

#### Scenario: Cogs use warn tier for stub gaps

- GIVEN cogs override sets `untyped-decorator-call = "warn"`
- WHEN `ty check bot/cogs/` runs
- THEN discord.py decorator gaps surface as warnings

#### Scenario: bot/ and tests/ are blocking

- GIVEN ty defaults to `error` for non-cog modules
- WHEN `ty check bot/ tests/` runs
- THEN any error diagnostic exits non-zero

#### Scenario: Warnings become fatal after gating

- GIVEN `error-on-warning = true` is enabled
- WHEN `ty check` encounters any warning-class diagnostic
- THEN the check exits non-zero

#### Scenario: Narrowing precedes gating

- GIVEN blanket `bot/cogs/**` / `tests/**` overrides still apply and known warnings are unfixed
- WHEN the warning gate is not yet enabled
- THEN enabling it is deferred until fixes land and overrides shrink to per-file entries

### Requirement: Coverage gate ratchet in pytest addopts

`pyproject.toml` MUST configure `addopts = "--cov=bot --cov-fail-under=75"` as the final coverage gate.

#### Scenario: Gate at 75%

- GIVEN `addopts` sets `--cov-fail-under=75`
- WHEN `pytest` runs
- THEN the run fails if `bot/` coverage is below 75%

### Requirement: Warning filter allowlist

`pyproject.toml` MUST configure `filterwarnings` to suppress known benign warnings (e.g., discord.py's `asyncio.iscoroutinefunction` deprecation) so they do not cause test failures under `PYTHONASYNCIODEBUG=1`.

#### Scenario: Benign asyncio warning suppressed

- GIVEN `filterwarnings` suppresses the `iscoroutinefunction` deprecation
- WHEN tests run with `PYTHONASYNCIODEBUG=1`
- THEN the deprecation warning does not cause a test failure

### Requirement: pytest-randomly adopted with deterministic seed

`pytest-randomly` MUST be added as a dev dependency and MUST randomize test ordering by default. The default seed MUST be deterministic (fixed value) so that CI and local runs produce the same order unless explicitly reseeded.

#### Scenario: Tests run in random order by default

- GIVEN `pytest-randomly` is installed
- WHEN `pytest` runs without specifying a seed
- THEN tests execute in a randomized order using the default deterministic seed

#### Scenario: Deterministic seed produces same order

- GIVEN the default seed is fixed
- WHEN `pytest` runs twice with no code changes
- THEN both runs produce the identical test execution order

### Requirement: Dev dependencies declared

Dev dependencies MUST be declared via PEP 735 `[dependency-groups] dev`, NOT `[project.optional-dependencies] dev`. The dev group MUST include ruff==0.15.20, ty (exact pin e.g. ty==0.0.18), pytest, pytest-asyncio, pytest-cov, pytest-randomly, hypothesis, freezegun. MUST NOT include mypy, bandit, pip-audit. prek/tach/zizmor are non-Python and installed separately. `[tool.uv] default-groups = ["dev"]` MUST exist.

#### Scenario: Dependency groups installable

- GIVEN `[dependency-groups] dev` lists required tools
- WHEN `uv sync --locked` runs
- THEN all dev tools are installed

#### Scenario: Default group auto-installs dev

- GIVEN `[tool.uv] default-groups = ["dev"]`
- WHEN `uv sync` runs without `--no-default-groups`
- THEN dev tools install without `--extra dev`

### Requirement: uv lockfile freshness enforced

`uv.lock` MUST be regenerated after dependency-group migration and ty addition. `uv lock --check` MUST exit zero. Lockfile MUST NOT contain mypy, bandit, or pip-audit entries.

#### Scenario: Lock matches pyproject

- GIVEN `uv.lock` is regenerated
- WHEN `uv lock --check` runs
- THEN it exits zero

#### Scenario: Stale lock detected

- GIVEN `pyproject.toml` is modified without regenerating
- WHEN `uv sync --locked` runs
- THEN it exits non-zero

<!-- BEGIN DELTA: ops-zero-lite (pyproject-toml-qa-config) -->
## ADDED Requirements

### Requirement: Vulture dead-code from advisory to blocking

Vulture MUST flip from advisory to blocking in `.github/workflows/code-quality.yml`: remove `continue-on-error: true` from the `vulture — dead code report` step (config-only clean per #4700 — ImageService deleted, advisory-clean at S5a `c641...`). Command MUST be `vulture bot/ --min-confidence 80`. Zero findings MUST be the gate; any new dead code at confidence ≥80 fails CI.

#### Scenario: Advisory flag removed

- GIVEN `.github/workflows/code-quality.yml` is parsed
- WHEN locating the vulture step
- THEN `continue-on-error` is absent/false (blocking)

#### Scenario: Vulture reports zero at 80

- GIVEN `vulture bot/ --min-confidence 80` runs on current tree
- WHEN executed
- THEN exit 0 with zero findings

#### Scenario: New dead code blocks PR

- GIVEN a new unused function/class is added to `bot/`
- WHEN vulture runs in CI at 80 confidence
- THEN step fails and PR is blocked

<!-- END DELTA: ops-zero-lite (pyproject-toml-qa-config) -->
