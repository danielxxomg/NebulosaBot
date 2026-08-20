# Delta for pyproject-toml-qa-config

## MODIFIED Requirements

### Requirement: Ruff configuration present

`pyproject.toml` MUST contain `[tool.ruff]` with `target-version = "py311"`, `line-length = 120`. Ruff MUST resolve to `0.15.20` via lock. `select` MUST retain `E,W,F,I,N,UP,B,SIM,RUF,S,C4,C90,RET,T20,ARG,DTZ,EM,T10,TRY,RSE,FLY,PERF,FURB` and add preview `ANN`, `PYI`, `PGH003` for ty alignment. `[tool.ruff.lint.mccabe]` MUST set `max-complexity = 15`. Test files MUST retain `S101`, `ARG`, `T20` ignores. The broad `bot/**/*.py` suppression (17 rules) MUST be removed progressively across PR4 batches A/B/C.

(Previously: broad bot/** suppression; no ANN/PYI/PGH003 preview)

#### Scenario: Preview rules for ty alignment enabled

- GIVEN `ANN`, `PYI`, `PGH003` are in `select` with preview
- WHEN `ruff check bot/` runs
- THEN annotation and type-ignore-comment rules are enforced

#### Scenario: bot/** suppression removed progressively

- GIVEN PR4 batches A (TRY003/EM101/EM102), B (S101/S310/S311/S110), C (ARG/TRY300/FURB/C901/F841) are applied
- WHEN `ruff check bot/` runs after all batches
- THEN zero findings are reported

#### Scenario: Test files retain exceptions

- GIVEN `tests/**/*.py` ignores include `S101`, `ARG`, `T20`
- WHEN `ruff check tests/` runs
- THEN test assertions and prints do not trigger violations

### Requirement: Dev dependencies declared

Dev dependencies MUST be declared via PEP 735 `[dependency-groups] dev`, NOT `[project.optional-dependencies] dev`. The dev group MUST include ruff==0.15.20, ty (exact pin e.g. ty==0.0.18), pytest, pytest-asyncio, pytest-cov, pytest-randomly, hypothesis, freezegun. MUST NOT include mypy, bandit, pip-audit. prek/tach/zizmor are non-Python and installed separately. `[tool.uv] default-groups = ["dev"]` MUST exist.

(Previously: PEP 503 extras including mypy/bandit)

#### Scenario: Dependency groups installable

- GIVEN `[dependency-groups] dev` lists required tools
- WHEN `uv sync --locked` runs
- THEN all dev tools are installed

#### Scenario: Default group auto-installs dev

- GIVEN `[tool.uv] default-groups = ["dev"]`
- WHEN `uv sync` runs without `--no-default-groups`
- THEN dev tools install without `--extra dev`

## REMOVED Requirements

### Requirement: Mypy configuration present

(Reason: ty replaces mypy; `[tool.mypy]` and all `[[tool.mypy.overrides]]` deleted)
(Migration: `[tool.ty.*]` with equivalent environment and per-module overrides)

### Requirement: Bandit configuration present

(Reason: Ruff S is strictly broader — 97 vs 95 findings; `[tool.bandit]` deleted)
(Migration: Ruff `S` in select list; bandit hooks/Makefile/CI removed in respective specs)

## ADDED Requirements

### Requirement: ty configuration present

`pyproject.toml` MUST contain `[tool.ty]`. `[tool.ty.environment]` MUST set `python-version = "3.11"`. Baseline `[tool.ty.rules]` MUST apply Astral's strict ruleset. `[[tool.ty.overrides]] include = ["bot/cogs/**"]` MUST set `untyped-decorator-call` and `possibly-unresolved-import` to `warn` (discord.py stub gaps). `bot/` and `tests/` MUST be `error`-blocking outside cog overrides. Inline suppression MUST use `# ty: ignore[<rule>]`.

#### Scenario: Cogs use warn tier for stub gaps

- GIVEN cogs override sets `untyped-decorator-call = "warn"`
- WHEN `ty check bot/cogs/` runs
- THEN discord.py decorator gaps surface as warnings

#### Scenario: bot/ and tests/ are blocking

- GIVEN ty defaults to `error` for non-cog modules
- WHEN `ty check bot/ tests/` runs
- THEN any error diagnostic exits non-zero

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
