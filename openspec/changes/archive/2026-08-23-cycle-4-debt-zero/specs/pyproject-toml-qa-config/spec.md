# Delta for pyproject.toml QA Configuration

## MODIFIED Requirements

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
