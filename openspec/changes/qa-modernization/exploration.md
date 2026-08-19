# Exploration: qa-modernization (SDD Cycle 2)

**Cycle**: 2 — QA/tooling migration to modern stack
**Preflight** (inherited from Cycle 1): Execution mode=auto, Artifact store=openspec, Delivery strategy=auto-chain, Review budget=1200 lines (caller override — openspec/config.yaml `review_budget_lines: 400` and `chained_pr_strategy: ask-always` apply per-slice, not change-wide)
**Strict TDD**: true (pytest-asyncio, bot/ 87.85% coverage, 2101 tests collected)

## Current State

NebulosaBot runs a **functional but legacy QA stack** established in the archived `rama-c-qa-tooling` (2026-06-27) and refined through `cleanup-stability` (Cycle 1, 2026-08-17). The tooling works (master is green, 2101 tests, 87.85% coverage, mypy 0 errors) but carries debt the user wants retired. Verified on disk at HEAD (pyproject.toml mtime 2026-08-19 17:14, uv.lock mtime 2026-08-18 23:57 — **lock is stale relative to pyproject**).

### Tooling inventory (verified by running each binary)

| Tool | Installed | Version | Source |
|------|-----------|---------|--------|
| uv | ✅ | 0.12.5 | system (astral-sh/uv) |
| ruff | ✅ | 0.15.20 | pyproject `[project.optional-dependencies] dev` |
| mypy | ✅ | 2.1.0 | pyproject `[project.optional-dependencies] dev` |
| bandit | ✅ | 1.9.4 | pyproject `[project.optional-dependencies] dev` |
| **ty** | ❌ NOT INSTALLED | — | (astral-sh/ty) |
| **prek** | ❌ NOT INSTALLED | — | (j178/prek) |
| **tach** | ❌ NOT INSTALLED | — | (tach-org/tach) |
| **zizmor** | ❌ NOT INSTALLED | — | (zizmorcore/zizmor) |

**Four of the seven target tools are absent from the environment and the lockfile.** This is a net-new adoption, not a config migration.

### Configuration inventory

**`pyproject.toml`** (146 lines) — single source of truth, already uv-managed:
- `[project]` requires-python = ">=3.11", dependencies = 6 runtime packages (discord.py, pillow, supabase, python-dotenv, PyJWT[crypto], psycopg[binary])
- `[project.optional-dependencies] dev = [...]` — 9 dev tools as PEP 503 extras (published in package metadata as `nebulosabot[dev]`)
- `[tool.ruff]` target-version="py311", line-length=120, **14 rule families selected** (E,W,F,I,N,UP,B,SIM,RUF,S,C4,C90,RET,T20,ARG,DTZ,EM,T10,TRY,RSE,FLY,PERF,FURB)
- `[tool.ruff.lint.mccabe]` max-complexity=15
- `[tool.ruff.lint.per-file-ignores]` — **massive bot/** suppression**: `"bot/**/*.py" = ["S", "C4", "C90", "T20", "ARG", "DTZ", "EM", "T10", "TRY003", "TRY004", "TRY300", "TRY301", "FLY", "PERF", "FURB", "RUF059", "F841"]` (17 rules disabled across all production code — "PR1 broad debt allowances ... PR2-PR5 will progressively remove")
- `[tool.mypy]` strict=true, python_version="3.11", **2 overrides** (bot.cogs.* disables 3 codes, tests.* disables 9 codes)
- `[tool.bandit]` exclude_dirs=["tests", "dashboard"]
- `[tool.pytest.ini_options]` asyncio_mode="auto", testpaths=["tests"], addopts="--cov=bot --cov-fail-under=75 --randomly-seed=42", markers=[live], filterwarnings=["error", ... 6 explicit ignores]

**`.pre-commit-config.yaml`** (49 lines) — classic pre-commit YAML:
- 4 repos: pre-commit-hooks v5.0.0 (trailing-whitespace, end-of-file-fixer, check-yaml, check-added-large-files), ruff-pre-commit v0.15.20 (ruff --fix, ruff-format --check), local mypy (`uv run mypy bot/`), local bandit, local gga
- `files: "^(bot/|tests/)"` scoping already correct

**`Makefile`** (35 lines) — 8 targets: lint, type (mypy), security (bandit), lint-full, type-full, test, cov, ci (chains lint+type+security+test+cov), audit (`uv run --with pip-audit pip-audit -l --strict`)

**`.github/workflows/ci.yml`** (104 lines) — QA matrix job:
- Triggers: push any branch, PR to master, weekly cron (Sundays 06:00 UTC)
- Matrix: Python 3.11, 3.12, 3.13, 3.14 (fail-fast: false)
- `PYTHONASYNCIODEBUG: "1"` env set (✅ already matches target)
- Steps: checkout@v4, setup-python@v5, cache uv, `pip install uv && uv sync --extra dev`, ruff check, ruff format check, **mypy**, **bandit**, **pip-audit** (`uv run --extra dev --with pip-audit pip-audit -l --strict`), pytest --cov-fail-under=75, upload coverage (3.12)
- Separate `dashboard-tests` job (Node 20, npm ci, tsc, vitest)
- Separate `pip-audit-weekly` job (schedule-only)

**`.github/workflows/code-quality.yml`** (34 lines) — report-only: jscpd (duplication), vulture (dead code). Triggers on PR to `main` (⚠️ mismatch — repo default is `master`).

### No tach.toml exists
No `.tach.toml` or `tach.toml` in repo root. Module boundary enforcement is currently zero — the layered architecture is enforced only by convention and review.

## Affected Areas

- **`pyproject.toml`** — central config: `[project.optional-dependencies]` → `[dependency-groups]` migration, add `[tool.ty.*]`, add `[tool.uv]` default-groups, remove `[tool.mypy]`, remove `[tool.bandit]`, expand/contract `[tool.ruff.lint]` select (add ANN/PYI/PGH003 preview for ty), remove bot/** global suppression progressively.
- **`uv.lock`** — stale (pyproject newer than lock); must regenerate after dependency-group migration + add ty/prek/tach entries; remove mypy/bandit/pip-audit entries.
- **`.pre-commit-config.yaml`** → **`prek.toml`** — full replacement. YAML → TOML. pre-commit-hooks repo → prek `repo: builtin` (all 4 hooks have parity). Local mypy hook → ty. Local bandit hook → DELETE (replaced by ruff S). Local gga hook → KEEP (system, stages: pre-commit). Add pre-push stage: `uv check` + `tach check`.
- **`Makefile`** — `type` target mypy → ty; `security` target bandit → DELETE (folded into `lint` via ruff S); `audit` target pip-audit → `uv audit`; add `tach` target (`tach check` + `tach check-external`).
- **`.github/workflows/ci.yml`** — replace setup-python+cache-uv with setup-uv action; replace mypy step with ty; delete bandit step; replace pip-audit step with `uv audit`; add `tach check` + `tach check-external` steps; add zizmor step (blocking, SHA-pinned); bump matrix coverage upload artifact from 3.12.
- **`.github/workflows/code-quality.yml`** — fix `main` → `master` trigger; consider folding jscpd/vulture into zizmor-augmented QA workflow or keep report-only.
- **`requirements.txt`** — Pterodactyl runtime pin file (discord.py==2.7.1, supabase==2.31.0, python-dotenv==1.2.2, Pillow==12.2.0). **Must remain pip-installable** — Pterodactyl panel uses pip, not uv. Source of truth stays pyproject.toml + uv.lock; this file is a pinned subset. No change needed unless dependency-groups migration breaks the pin derivation (it should not — runtime deps stay in `[project] dependencies`).
- **`bot/**/*.py`** — 426 latent ruff violations surface when bot/** ignores removed (135 TRY003 + 95 EM101 + 92 S101 + 44 EM102 + 11 TRY300 + 10 ARG002 + ...). 46 `# type: ignore` comments, 9 `cast(` calls, ~82 `Any` signatures — ty will re-evaluate all.
- **`tests/**/*.py`** — 177 `# type: ignore` comments, mypy tests.* override disables 9 codes. ty conversion must preserve test-suite green (2101 tests).
- **OpenSpec specs (existing)** — 4 specs encode the OLD tooling and MUST be superseded by delta specs: `pyproject-toml-qa-config` (mandates mypy strict + bandit + 14 ruff families), `pre-commit-config-file` (mandates .pre-commit-config.yaml with mypy/bandit hooks), `ci-workflow-file` (mandates mypy/bandit/pip-audit steps), `makefile-dx` (mandates mypy/bandit targets). The `qa-pre-commit` spec also exists.

## Real bot/ import graph (for Tach boundaries)

Verified by grep of all 79 bot/*.py files. Architecture is **cleanly layered with ONE violation**.

```
bot/
├── bot.py              (NebulosaBot — root, imported by 24 modules via TYPE_CHECKING)
├── __main__.py         (entrypoint)
├── config.py           (ServiceRoleValidationError, validate_supabase_key)
├── constants.py        (FALLBACK_PREFIX)
├── core/               ← Layer: core (foundation — no upward imports)
│   ├── context.py      (NebulosaContext — 13 importers)
│   ├── i18n.py         (t, SLASH_DESCRIPTIONS — 24 importers, MOST IMPORTED)
│   ├── cache.py        (TTLCache, cache_key — 15 importers)
│   ├── database.py     (DatabaseBase aggregator — 11 importers, composes db mixins)
│   ├── realtime.py      (Supabase Realtime CDC)
│   └── db/             ← Layer: db (9 mixins: guild, greeting, economy, member, infraction, ticket, ticket_category, ticket_note, ticket_audit)
│       └── base.py      (_unwrap, DatabaseBase — 11 importers)
├── models/             ← Layer: models (dataclasses mirroring DB rows — 0 upward imports, pure data)
│   └── (guild, ticket, ticket_category, ticket_note, infraction, member, economy_config, greeting_config)
├── utils/              ← Layer: utils (embeds, brand, checks, paginator, time, timeparse, ticket_helpers — 25 importers for embeds alone)
│   └── ⚠️ ticket_helpers.py imports from bot.services.ticket_invariants (parse_ticket_ref) — THE ONE VIOLATION
├── services/           ← Layer: services (business logic — imports core/db/models/utils)
│   ├── (guild, greeting, economy, infraction, logging, image, transcript, schema_inventory, live_catalog, integrity_report)
│   └── ticket* (service facade decomposed into 8 modules — 3007 combined LOC; ticket_service.py is 450-line facade)
├── views/              ← Layer: views (Discord UI — imports core/models/utils, NOT services)
│   └── (confirmation, ticket_actions, ticket_category_select, ticket_panel, tickets)
├── cogs/               ← Layer: cogs (Discord interaction only — imports services/views/utils/core)
│   └── (core, greetings, ocio, sentinel, setup, stellar, utility, tickets + 4 ticket_*_flow)
└── listeners/          ← Layer: listeners (xp_listener, audit_listener — imports core/utils only)
```

**Tach layer hierarchy (recommended)**:
```
layers = ["cogs", "views", "services", "utils", "core", "db", "models"]
```
With constraints:
- `cogs` depends_on `views`, `services`, `utils`, `core`
- `views` depends_on `utils`, `core`, `models` (NOT services — currently clean)
- `services` depends_on `core`, `db`, `models`, `utils` (NOT cogs/views/listeners — currently clean)
- `utils` depends_on `core`, `models` (⚠️ ONE violation: ticket_helpers → services.ticket_invariants — must fix or grandfather)
- `core` depends_on `db`, `models` (database.py composes db mixins; i18n/cache/context are standalone)
- `db` depends_on `models` (DB mixins return model dataclasses)
- `models` depends_on `[]` (pure data — no imports)

**The single violation** (`bot/utils/ticket_helpers.py:17` importing `parse_ticket_ref` from `bot.services.ticket_invariants`) is the only structural debt Tach will flag. Decision needed: move `parse_ticket_ref` to a lower layer, or mark `utils` as unchecked for that edge.

## Approaches

### 1. Big-bang migration (single change, all 7 tools)

Convert all tooling in one proposal/spec/design/tasks cycle. Delete mypy/bandit/pip-audit/pre-commit-config in the same change that adds ty/prek/tach/zizmor/uv-audit/dependency-groups.

- **Pros**: Clean end state in one cycle; no transitional dual-config period; single verify gate.
- **Cons**: Enormous blast radius — touches pyproject.toml, uv.lock, 2 workflows, Makefile, prek.toml (new), tach.toml (new), zizmor.yml (new), 4 OpenSpec spec deltas, plus 426 latent ruff violations if bot/** ignores removed simultaneously. Violates the 1200-line review budget by 3-4x. ty is net-new (no baseline) so "28 deferred close" is guesswork without a first run. Rollback is all-or-nothing.
- **Effort**: Very High. **Not recommended.**

### 2. Stacked-to-main slices by tool family (auto-chain, 5-6 PRs)

Split by tool boundary so each PR is independently reviewable and revertible. Match Cycle 1's stacked strategy.

| Slice | Scope | Risk | Est. LOC |
|-------|-------|------|----------|
| PR1 — uv foundation | `[dependency-groups]` migration, `[tool.uv] default-groups`, regenerate uv.lock, setup-uv action in ci.yml, `uv audit` replaces pip-audit, delete requirements.txt sync logic (keep file) | Medium (PEP 735 breaks `pip install .[dev]` — Pterodactyl uses pip for runtime only, so OK) | ~250 |
| PR2 — ty replaces mypy | Add ty to dev group, `[tool.ty.*]` config (environment py311, strict rules, minimal overrides for cogs/tests), delete `[tool.mypy]`, convert Makefile + ci.yml + prek hooks, run baseline → defer 28 | High (ty net-new; discord.py py.typed present but stub gaps exist; reportMissingTypeStubs NOT supported by ty yet — #3638) | ~300 |
| PR3 — prek replaces pre-commit | prek.toml (builtin hooks + ruff + ty + gga local + pre-push uv check+tach), delete .pre-commit-config.yaml | Low-Medium (prek builtin parity confirmed for all 4 hooks; TOML format; pre-push stage new) | ~200 |
| PR4 — Ruff debt removal (progressive) | Remove bot/** global suppression rule-by-rule; add ANN/PYI/PGH003 preview for ty; fix 426 latent violations in batches (TRY003/EM101/EM102 are 274 of 426 — mostly mechanical message style) | Medium-High (92 S101 asserts need real fixes, not suppression; 30 security findings S310/S311/S110 need review) | ~600 |
| PR5 — Security: bandit delete + zizmor | Verify Ruff S parity with bandit (95 LOW bandit findings ↔ 97 ruff S findings — near-identical, both dominated by B101/S101 assert), delete bandit config + hooks + Makefile target, add zizmor.yml + zizmor-action workflow (blocking, SHA-pinned) | Low (parity confirmed; zizmor is additive) | ~200 |
| PR6 — Tach boundaries | tach.toml on real architecture (7 layers, 7+ modules, 1 known violation), `tach check` + `tach check-external` in ci.yml + pre-push, fix or grandfather the utils→services violation | Medium (baseline not a refactor — capture current state, then enforce) | ~250 |

- **Pros**: Each PR ≤ review budget (1200 change-wide, 400 per-slice per openspec config); independent rollback; ty baseline established in PR2 before debt removal in PR4; matches Cycle 1 proven strategy.
- **Cons**: 6 PRs is more coordination; transitional period where both mypy and ty configs coexist (brief — PR2 deletes mypy); ty stub-gap discovery may force PR2 scope expansion.
- **Effort**: Medium-High overall, but distributed.

### 3. Minimal-impact (keep mypy, add ty alongside, no bandit delete)

Adopt new tools without removing old ones. Run ty in parallel, keep bandit, keep pre-commit.

- **Pros**: Zero rollback risk; gradual adoption.
- **Cons**: Does not satisfy the user's "migrate completely" intent (user prompt: "migra completamente el stack"). Duplicates config, doubles CI time, confuses contributors about source of truth. Leaves debt.
- **Effort**: Low. **Does not meet requirements.**

## Recommendation

**Use Approach 2 (stacked-to-main, 6 PRs) with two ordering constraints:**

1. **PR1 (uv foundation) must land first** — dependency-groups migration is the prerequisite for cleanly adding ty/prek/tach to the dev group and regenerating uv.lock once. All subsequent PRs depend on the new lock.
2. **PR2 (ty baseline) must land before PR4 (ruff debt removal)** — ty's type-check results will inform which `# type: ignore` and `cast()` can be removed; removing ruff ignores first creates churn ty may invalidate.

For PR4, **do NOT remove all bot/** ignores at once**. Remove in three sub-batches:
- Batch A (mechanical, ~274 violations): TRY003 + EM101 + EM102 — raise message style, auto-fixable patterns, low semantic risk.
- Batch B (security, ~97 violations): S101 assert → replace with real raises or `if ... else`; S310/S311/S110 → case-by-case review. Keep S101 suppressed in tests/ permanently (already done).
- Batch C (quality, ~55 violations): ARG, TRY300/301, FURB, C901, F841 — address individually.

**For Tach (PR6)**: capture the current architecture as the baseline. Do NOT use tach as a pretext for a refactor — the user's LOC history shows S3 facade decomposition REDISTRIBUTED code (ticket_service 2088→450, but 8 combined service modules grew to 3007) rather than trimming it. Tach's job is to PREVENT regressions, not to force a reshape. The one known violation (utils/ticket_helpers → services/ticket_invariants) should be grandfathered with a `deprecated` dependency or fixed by moving `parse_ticket_ref` to `bot/core/` or `bot/models/ticket.py`.

**For ty discord.py stub gap**: ty does NOT yet support `reportMissingTypeStubs`/`import-untyped` (tracked #3638). discord.py ships `py.typed` (verified in .venv), so ty reads discord.py's inline types directly — the gap is smaller than a stub-less library. Start with `[[tool.ty.overrides]] include = ["bot/cogs/**"]` with `untyped-decorator-call` and `possibly-unresolved-import` set to `warn` (not error) for the baseline, then tighten. Target: bot/ and tests/ blocking with 28 deferred is achievable but requires a first dry run to enumerate the actual ty findings — the "28 deferred" figure in the user prompt is a target, not a measured baseline.

## Risks

- **PEP 735 dependency-groups breaks `pip install .[dev]`**: `[dependency-groups]` are NOT published in package metadata (unlike `[project.optional-dependencies]`). NebulosaBot is published to PyPI as `nebulosabot` (classifiers present), but the Pterodactyl panel uses `requirements.txt` (pinned runtime deps, pip-resolved) — NOT `pip install nebulosabot[dev]`. The dev extras are consumed only via `uv sync --extra dev` today, so migration to `uv sync` (default-groups) is safe. **Verify no external consumer relies on `pip install nebulosabot[dev]`** before migrating.

- **ty is pre-1.0 (Context7 shows version 0.0.18)**: ty's ruleset, config keys, and override semantics may change between minor versions. Pinning `ty>=0.0.18` in dependency-groups is required; a ty release could break CI. Mitigation: pin exact version (e.g. `ty==0.0.18`) and run `uv lock --upgrade-package ty` deliberately.

- **ty stub gap for discord.py**: Although discord.py ships `py.typed`, its inline type annotations are incomplete in places (especially around `commands.Cog` hybrid_command decorators, `Context` generics, and `app_commands` locale_str). mypy currently suppresses this via `bot.cogs.* disable_error_code = ["untyped-decorator", "arg-type", "unused-ignore"]`. ty's equivalent rules (`untyped-decorator-call`, `invalid-argument-type`) will surface these. The "no Any/cast silencing" target may be unachievable for cogs without upstream discord.py fixes — realistic outcome is cogs stay at `warn`, services/core/models/views/listeners reach `error`-blocking.

- **prek is also pre-1.0 and a separate binary**: prek must be installed via cargo, npm, or downloaded release binary — it is NOT a Python package and cannot go in dependency-groups. CI must install prek separately (e.g. `pip install prek` if wheels exist, or a setup step). The `.pre-commit-config.yaml` → `prek.toml` conversion has a built-in tool (`prek util convert`) but the builtin hooks repo (`repo: builtin`) is prek-specific and not portable back to pre-commit.

- **Bandit → Ruff S parity is NOT exact**: Bandit finds 95 LOW-severity issues (all B101 assert_used, high confidence). Ruff S finds 97 (92 S101 + 2 S310 + 2 S311 + 1 S110). The 2-issue delta is Ruff catching S310 (suspicious-url-open-usage) and S311 (suspicious-non-cryptographic-random-usage) that Bandit does NOT flag — Ruff S is STRICTLY broader. Deleting bandit loses zero coverage. However, Bandit's B-families beyond B101 (e.g. B503, B604 for subprocess/crypto) are NOT all covered by Ruff S — a delta audit is needed if those matter. Current bandit output shows ONLY B101, so for this codebase the parity is complete.

- **zizmor SHA-pinning will flag existing workflows**: ci.yml uses `actions/checkout@v4`, `actions/setup-python@v5`, `actions/cache@v4`, `actions/upload-artifact@v4` — all tag-pinned, not SHA-pinned. zizmor's `unpinned-uses` audit (default conservative policy) will FAIL on the first run. Fixing requires pinning all actions to commit SHAs (e.g. `actions/checkout@<40-char-sha> # v4`). This is a deliberate hardening step, not a regression.

- **Ruff 0.15.20 may not be latest**: Caller noted "ruff 0.15.20 vs current" — verify against PyPI. Ruff releases weekly. If a newer version adds/changes rules, the 426-violation debt count may shift.

- **uv.lock staleness**: pyproject.toml (2026-08-19 17:14) is NEWER than uv.lock (2026-08-18 23:57). The lockfile does not reflect the latest pyproject changes. `uv lock` must run before any dependency-group migration to establish a clean baseline.

- **code-quality.yml triggers on `main` but repo default is `master`**: This workflow has never run on PRs. Either fix the trigger or delete the workflow (its jscpd/vulture reports are subsumed by zizmor + ruff).

- **S3 facade LOC history confirms refactors redistribute, not trim**: ticket_service.py went 2088→450 (facade) but the 8 combined ticket service modules total 3007 LOC — net +919 LOC from decomposition. bot/ total is 17260 (matches user claim). This means tach boundaries should be captured on the CURRENT decomposed architecture, not a hypothetical future simplification. Do not use tach to justify another decomposition refactor.

- **Review budget**: openspec/config.yaml sets `review_budget_lines: 400` per slice and `chained_pr_strategy: ask-always`. The caller's inherited "1200" is the change-wide budget (3 slices × 400). With 6 recommended PRs, the orchestrator must confirm whether the budget allows 6 slices or must compress to 4-5. PR4 (ruff debt, ~600 LOC) may need splitting into PR4a/PR4b to respect the 400-line per-slice limit.

## Ready for Proposal

**No, not yet.** The technical direction is clear (Approach 2, stacked-to-main, 6 PRs), but the proposal must first resolve:

1. **Slice count vs review budget**: Does the 1200-line change-wide budget (caller override) permit 6 slices, or must PR4 (ruff debt) be pre-split into PR4a/PR4b to keep each slice ≤400 lines?
2. **ty baseline measurement**: Before committing to "28 deferred, no Any/cast silencing", run `ty check bot/` once (after PR1 lands) to get the ACTUAL finding count. The 28 is a target, not evidence. If ty surfaces 200+ findings in cogs due to discord.py stub gaps, the cogs-override policy must be decided (warn vs error vs suppress).
3. **PEP 735 migration confirmation**: Confirm no external consumer runs `pip install nebulosabot[dev]` (Pterodactyl uses requirements.txt, so likely safe — but verify).
4. **Tach violation disposition**: Fix `bot/utils/ticket_helpers.py → bot/services/ticket_invariants` import (move `parse_ticket_ref` down to core/models), or grandfather as `deprecated` dependency in tach.toml?
5. **zizmor SHA-pinning acceptance**: Confirm the user wants all GitHub Actions SHA-pinned (hardens against supply-chain attacks but complicates Dependabot updates — every action bump becomes a SHA lookup).
6. **code-quality.yml fate**: Fix trigger (main→master), delete (subsumed by zizmor+ruff), or keep as report-only?
7. **Ruff version**: Bump to latest (verify >0.15.20 exists) or pin 0.15.20 for stability through the cycle?

Once these are answered, Approach 2 is ready for proposal. No spec or design has been created in this exploration.
