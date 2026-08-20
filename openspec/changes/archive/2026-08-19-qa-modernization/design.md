# Design: QA Modernization

> Sources: proposal.md, exploration.md, 7 specs, verified ty/tach/prek/uv docs (Context7), real `bot/` import graph (CodeGraph). Rule names verified against ty 0.0.18 `register_lints` registry.

## Technical Approach

Migrate NebulosaBot's legacy QA stack (mypy/bandit/pip-audit/pre-commit/extras) to a modern Astral-native stack (ty/Ruff S/uv audit/zizmor/prek/tach/PEP 735 groups) via stacked-to-main slices. Each slice is independently revertible and respects the 1200-line change-wide / 400-line per-slice review budget. The design captures the **current** architecture and tooling — it does NOT use tach as a pretext for refactoring (S3 LOC history confirms decompositions redistribute, not trim).

## Architecture Decisions

### Decision: Stacked-to-main, 6 PRs (Approach 2)

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Big-bang single change | Clean end-state, but 3-4× over budget, ty baseline guesswork, all-or-nothing rollback | ❌ Rejected |
| 6 stacked slices | Each ≤400 LOC, independent rollback, ty baseline before debt removal | ✅ Chosen |
| Minimal (add, don't remove) | Zero rollback risk, but duplicates config, doubles CI, violates "migrate completely" intent | ❌ Rejected |

**Rationale**: Cycle 1 (cleanup-stability) proved the stacked strategy. PR2-before-PR4 constraint lets ty findings inform which `# type: ignore`/`cast()` ruff can safely remove.

### Decision: ty rule names — correct the spec

**Choice**: Use the REAL ty 0.0.18 rule names, not the prompt's assumed names.
**Alternatives**: Blindly adopt prompt's `untyped-decorator-call`/`possibly-unresolved-import`.
**Rationale**: Verified against ty's `register_lints` registry (diagnostic.rs). The prompt's names do NOT exist:
- `untyped-decorator-call` → use `invalid-argument-type` (decorator args)
- `possibly-unresolved-import` → use `possibly-missing-import` + `possibly-unresolved-reference`
- `unsound-return` → real name is `unsound-return-statement`
- `blanket-ignore-comment`, `missing-type-argument`, `possibly-unresolved-reference` → confirmed correct.

### Decision: Tach violation — move + re-export shim

**Choice**: Move `parse_ticket_ref` + `TicketRef` to `bot/core/ticket_ref.py`, keep a re-export in `bot/services/ticket_invariants.py` for the 8 existing importers (ticket_repair_service, ticket_service, ticket_lifecycle_service + 5 test files).
**Alternatives**: (b) `deprecated = true` grandfather; pure move touching all importers.
**Rationale**: Pure move has 8+ file blast radius (verified via grep). The re-export shim makes the move zero-churn for importers while satisfying `utils depends_on [core, models]` — utils imports from core, not services. `deprecated=true` would leave real debt. Spec requires resolution, not `unchecked=true`.

### Decision: PEP 735 migration is safe for Pterodactyl

**Choice**: `[dependency-groups] dev` + `[tool.uv] default-groups = ["dev"]`; delete `[project.optional-dependencies] dev`.
**Rationale**: Pterodactyl uses `requirements.txt` (pinned runtime deps via pip), NOT `pip install nebulosabot[dev]`. Dev extras are consumed only via `uv sync --extra dev` today. PEP 735 groups are NOT published to package metadata — acceptable since no external consumer relies on `[dev]`.

### Decision: Pin ty==0.0.18 exact

**Choice**: Exact pin, not `>=0.0.18`. Deliberate `uv lock --upgrade-package ty`.
**Rationale**: ty is pre-1.0; its ruleset/config keys change between minors (proven: prompt's assumed rule names were wrong). Exact pin prevents silent CI breakage.

## Data Flow

```
Developer commit ──► prek (pre-commit stage)
  builtin (trailing-ws/eof/yaml/large-files)
    └─► ruff check --fix  ──► ruff format --check
          └─► ty check bot/ tests/  ──► GGA (.gga)

git push ──► prek (pre-push stage)
  uv check ──► tach check ──► tach check-external

CI (ci.yml) ──► 3 jobs
  quality: uv sync --locked → ruff check → ruff format --check
            → uv check --all-packages → tach check → tach check-external
            → uv audit
  tests:   matrix[3.11-3.14] PYTHONASYNCIODEBUG=1 pytest --cov-fail-under=75
  workflow-security: zizmor (SHA-pinned, SARIF/github, blocking)

Weekly schedule ──► quality job (uv audit) + tests
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `pyproject.toml` | Modify | extras→groups, `[tool.uv] default-groups`, `[tool.ty.*]`, add ANN/PYI/PGH003 preview, delete `[tool.mypy]`/`[tool.bandit]`, progressive bot/** removal |
| `uv.lock` | Regenerate | Add ty/prek/tach; remove mypy/bandit/pip-audit |
| `prek.toml` | Create | builtin + ruff + ty + gga local + pre-push uv check + tach |
| `.pre-commit-config.yaml` | Delete | Replaced by prek.toml |
| `tach.toml` | Create | 7 layers, 8+ modules, interfaces, strict flags |
| `bot/core/ticket_ref.py` | Create | `parse_ticket_ref` + `TicketRef` moved here |
| `bot/services/ticket_invariants.py` | Modify | Re-export `parse_ticket_ref`/`TicketRef` from core (shim) |
| `bot/utils/ticket_helpers.py` | Modify | Import from `bot.core.ticket_ref` (fixes violation) |
| `.github/workflows/ci.yml` | Modify | setup-uv SHA, 3 jobs, ty/tach/uv audit/zizmor, delete pip-audit-weekly |
| `.github/workflows/code-quality.yml` | Modify | Fix `main`→`master` trigger |
| `Makefile` | Modify | type→ty, delete security(bandit), audit→uv audit, add tach |
| `bot/**/*.py` | Modify | 426 ruff fixes (PR4 batches), 46 type:ignore review |
| `tests/**/*.py` | Modify | Preserve 177 type:ignore (ty tests.* override), green |

## Interfaces / Contracts

### tach.toml (verified format against `/tach-org/tach`)

```toml
exclude = ["**/*__pycache__", "build/", "dist/", "dashboard/", "locales/"]
source_roots = ["."]
exact = true
forbid_circular_dependencies = true
ignore_type_checking_imports = true
respect_gitignore = true
root_module = "ignore"

layers = ["cogs", "views", "services", "utils", "core", "db", "models"]

[[modules]]
path = "bot.cogs"
layer = "cogs"
depends_on = ["bot.views", "bot.services", "bot.utils", "bot.core"]

[[modules]]
path = "bot.views"
layer = "views"
depends_on = ["bot.utils", "bot.core", "bot.models"]

[[modules]]
path = "bot.services"
layer = "services"
depends_on = ["bot.core", "bot.core.db", "bot.models", "bot.utils"]

[[modules]]
path = "bot.utils"
layer = "utils"
depends_on = ["bot.core", "bot.models"]

[[modules]]
path = "bot.listeners"
layer = "utils"          # listeners sit at utils tier (imports core/utils only)
depends_on = ["bot.core", "bot.utils"]

[[modules]]
path = "bot.core"
layer = "core"
depends_on = ["bot.core.db", "bot.models"]

[[modules]]
path = "bot.core.db"
layer = "db"
depends_on = ["bot.models"]

[[modules]]
path = "bot.models"
layer = "models"
depends_on = []

[[interfaces]]
expose = ["parse_ticket_ref", "TicketRef"]
from = ["bot.core.ticket_ref"]

[[interfaces]]
expose = ["Ticket", "TicketNote", "TicketCategory"]
from = ["bot.models"]

[external]
exclude = ["pytest", "hypothesis", "freezegun"]   # dev/test-only, not runtime
rename = ["PIL:pillow", "psycopg:psycopg"]        # module→package map
```

### ty config in pyproject.toml (verified against `/astral-sh/ty`)

```toml
[tool.ty.environment]
python-version = "3.11"

[tool.ty.rules]
# Astral strict recommendation (docs/coming-from-mypy-or-pyright.md)
missing-type-argument = "error"
possibly-unresolved-reference = "warn"      # discord.py stub gaps
unsound-return-statement = "error"
blanket-ignore-comment = "error"

[tool.ty.analysis]
strict-literal-narrowing = true
strict-generic-narrowing = true

# Cogs override — discord.py inline py.typed gaps (decorator/locale_str)
[[tool.ty.overrides]]
include = ["bot/cogs/**"]

[tool.ty.overrides.rules]
invalid-argument-type = "warn"              # untyped-decorator-call equivalent
possibly-missing-import = "warn"
possibly-unresolved-reference = "warn"

# tests/ override — preserve test-suite green (177 type:ignore)
[[tool.ty.overrides]]
include = ["tests/**"]

[tool.ty.overrides.rules]
possibly-unresolved-reference = "warn"
possibly-missing-attribute = "warn"
```

**discord.py stub gap**: discord.py ships `py.typed` (verified in .venv). ty reads inline types directly. `reportMissingTypeStubs`/`import-untyped` NOT supported by ty (#3638) — gap is bounded, not a blocker. Inline suppression: `# ty: ignore[<rule>]`.

### prek.toml (verified against `/j178/prek`)

```toml
[priorities]
builtin = 0
format = 10
lint = 20
type = 30
gga = 40
push = 50

[[repos]]
repo = "builtin"
hooks = [
  { id = "trailing-whitespace" },
  { id = "end-of-file-fixer" },
  { id = "check-yaml" },
  { id = "check-added-large-files" },
]

[[repos]]
repo = "local"
hooks = [
  { id = "ruff-check", name = "ruff check", language = "system",
    entry = "uv run ruff check --fix", files = "^(bot/|tests/)",
    stages = ["pre-commit"], priority = "lint" },
  { id = "ruff-format", name = "ruff format", language = "system",
    entry = "uv run ruff format --check", files = "^(bot/|tests/)",
    stages = ["pre-commit"], priority = "format" },
  { id = "ty", name = "ty", language = "system",
    entry = "uv run ty check bot/ tests/", files = "^(bot/|tests/)",
    stages = ["pre-commit"], priority = "type" },
  { id = "gga", name = "GGA", language = "system",
    entry = "bash .gga", always_run = true, pass_filenames = false,
    stages = ["pre-commit"], priority = "gga" },
  # pre-push stage
  { id = "uv-check", name = "uv check", language = "system",
    entry = "uv check", always_run = true, pass_filenames = false,
    stages = ["pre-push"], priority = "push" },
  { id = "tach-check", name = "tach check", language = "system",
    entry = "uv run tach check", always_run = true, pass_filenames = false,
    stages = ["pre-push"], priority = "push" },
  { id = "tach-check-external", name = "tach check-external", language = "system",
    entry = "uv run tach check-external", always_run = true, pass_filenames = false,
    stages = ["pre-push"], priority = "push" },
]
```

### dependency-groups migration

```toml
[dependency-groups]
dev = [
  "pytest>=8.0", "pytest-asyncio>=0.23", "pytest-cov>=5.0",
  "pytest-randomly>=3.15", "hypothesis>=6.100", "freezegun>=1.5",
  "ruff==0.15.20", "ty==0.0.18",
]
# mypy, bandit, pip-audit REMOVED. prek/tach/zizmor installed separately (non-Python / CI-only).

[tool.uv]
default-groups = ["dev"]
```

`requirements.txt` (Pterodactyl) unchanged — runtime deps stay in `[project] dependencies`.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | ty/tach/ruff configs valid | `ty check`, `tach check`, `ruff check` exit 0 on baseline |
| Integration | prek hooks block on failure | stage a violation, assert non-zero exit |
| Integration | CI quality job gates | push branch with stale lock → `uv sync --locked` fails |
| E2E | full pipeline green | `make ci` runs lint→type→test→cov, 2101 tests pass, cov ≥75% |
| Regression | move of `parse_ticket_ref` | existing `tests/test_ticket_invariants.py` + contract tests pass unchanged |

## PR Sequence & Ordering

| PR | Slice | LOC | Constraint | Rollback |
|----|-------|-----|-----------|----------|
| 1 | uv foundation: groups, `[tool.uv]`, regen lock, setup-uv SHA, `uv audit`, delete pip-audit-weekly | ~250 | **MUST land first** — new lock is prerequisite for all | revert extras, restore pip-audit-weekly |
| 2 | ty: add ty==0.0.18, `[tool.ty.*]`, delete `[tool.mypy]`, Makefile/ci/prek ty, baseline → defer 28 | ~300 | **MUST land before PR4** — ty findings inform ruff ignore removal | restore `[tool.mypy]` |
| 3 | prek: prek.toml, delete `.pre-commit-config.yaml`, pre-push uv check + tach | ~200 | after PR2 (ty hook) | restore YAML |
| 4 | Ruff debt: remove bot/** suppression progressively | ~600 | after PR2; **3 sub-batches** | restore ignores |
| 5 | Security: bandit↔S parity run once → delete bandit, zizmor SHA-pin | ~200 | after PR4 (S stays enabled) | restore bandit |
| 6 | Tach: tach.toml, move `parse_ticket_ref`→core, CI+pre-push | ~250 | after PR3 (pre-push tach hook) | delete tach.toml |

### PR4 sub-batches (each ≤400)

| Batch | Scope | Violations | Risk |
|-------|-------|-----------|------|
| A (mechanical) | TRY003 + EM101 + EM102 message style | ~274 | Low — auto-fixable patterns |
| B (security) | S101 assert→real raises; S310/S311/S110 review | ~97 | Med — 30 need case-by-case review; S101 stays suppressed in tests/ |
| C (quality) | ARG, TRY300/301, FURB, C901, F841 | ~55 | Med — address individually |

**Ruff rule families**: keep all 14, ADD `ANN`/`PYI`/`PGH003` preview. `S` stays enabled to replace bandit. Fixes must be real, NOT broad ignores. `tests/**` keeps semantic exceptions only (S101/ARG/T20).

## Security

- **Bandit → Ruff S parity**: run BOTH once in PR5. Bandit=95 LOW (all B101 assert), Ruff S=97 (92 S101 + 2 S310 + 2 S311 + 1 S110). Ruff S is STRICTLY broader — deleting bandit loses zero coverage. Then delete `[tool.bandit]`, bandit hooks, Makefile `security` target.
- **uv audit** replaces pip-audit cron: runs in quality job + weekly schedule.
- **zizmor**: `workflow-security` job, blocking, `--format=github` (annotations) or `sarif` + `codeql-action/upload-sarif` (SHA-pinned). All `uses:` SHA-pinned: checkout, setup-uv, cache, upload-artifact, setup-node, zizmor-action.

## Migration / Rollout

- No data migration. No feature flags.
- Per-PR rollback via `git revert` (reverse order: PR6→PR1).
- `code-quality.yml`: fix `main`→`master` trigger (currently never runs on PRs). Keep jscpd/vulture report-only (subsumed by zizmor+ruff, but low cost to retain).
- `pip-audit-weekly` job deleted (spec: ci-workflow-file + workflow-security).

## Open Questions

- [ ] PR2 actual ty finding count: run `ty check bot/` post-PR1 to confirm "28 deferred" target vs reality. If cogs surface 200+ findings, decide warn-vs-error policy before PR4.
- [ ] zizmor SHA-pinning acceptance: every action bump becomes a SHA lookup (Dependabot friction). Confirm user wants this hardening.
- [ ] Ruff version: bump to latest (>0.15.20?) or pin 0.15.20 for cycle stability? 426-violation count may shift on newer rules.

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary. This change modifies config files and CI workflows; `bash .gga` and `uv run *` invocations are pre-existing trusted toolchain calls, not new process-integration surfaces.
