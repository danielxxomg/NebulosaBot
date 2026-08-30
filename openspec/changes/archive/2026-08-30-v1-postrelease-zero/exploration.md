# Exploration: v1-postrelease-zero

## Current State

**Change intent**: Restore real `v1.0.0` baseline (`70db4e3`, tag `v1.0.0`) and reconcile post-release drift. The change is NOT a feature — it is a quality-gate + spec-truth restoration. Verified at clean HEAD (worktree clean, `master==origin/master`, 29 migrations, `pyproject.toml --cov-fail-under=80`, `prek.toml` single-source):

- **`uv run pytest -q` (default addopts `--cov=bot --cov-fail-under=80 --randomly-seed=42`)**: `2954 passed, 19 skipped, 1 failed, 19 warnings`, **coverage 79.78%** (floor 80 → FAIL by 0.22% ≈ 22 lines on 9816 LOC). Single failure `tests/test_pr3_prek_replaces_precommit.py::TestPrekTomlExists::test_prek_run_all_files_exits_zero` — caused by the `ty` hook exiting 1 inside `prek run --all-files`. No warning filter lost (`filterwarnings = error` first, discord/Pillow ignores explicit). `tach` impact warning confirms that failure would be missed under impact analysis.
- **`uv run ruff check bot tests`**: PASS.
- **`uv run ty check`**: **80 diagnostics** — **66 in `bot/` (52 `unused-type-ignore`, 14 `unresolved-attribute`)** and **14 in `tests/` (8 `unused-type-ignore`, 4 `invalid-argument`, 2 `unresolved-attribute`)**. `prek` and `ty` share the same root cause. Direct `uvx prek run --all-files --no-progress` output confirms `ty` is the only failing hook; all other hooks (ruff, betterleaks, gga) pass.
- **AST status**: Zero real `hybrid_command`/`hybrid_group` registrations in `bot/cogs/*.py` (verified via `grep` + CodeGraph). Two docstring literals in `bot/utils/checks.py:229,361` (`@commands.hybrid_command(name="sync"/"warn")`) are examples only — scoped guard `tests/test_zero_hybrid_guard.py` is correct to check decorators, not substrings. Comma timer guard (`,`) and zero-hybrid guard: **4 passed**. `TicketsCog.on_message` comma invariant intact — `bot/bot.py:_noop_prefix` returns `[]` (`command_prefix=_noop_prefix`), `close-confirmation` spec unchanged.
- **OpenSpec sync**: 13 `clean-1.0` deltas mechanically synced at `70db4e3` (3 NEW exact, 10 MODIFIED merges no truncation, verified via `archive-report.md`). **Source-spec drift remains**: 12 older source specs retain **27 stale/conflicting hybrid/prefix references** — `economy-commands`, `utility-commands`, `docs-manual`, `slash-locale-translator`, `qa-help-builder`, `permission-model`, `sentinel-commands`, `ticket-commands`, `i18n-system`, `unclaim-command`, `setup-wizard`, `guild-config`. These are PRE-clean-1.0 specs that were never updated to the post-S6 slash-only truth (`bot-core` now mandates ZERO hybrids, `get_prefix -> []`, help shows slash only).
- **Archived verify staleness**: `openspec/changes/archive/2026-08-26-clean-1-0/verify-report.md` verdict `pass_with_warnings` claims `ty diagnostics tests-only, non-blocking` — this is **now stale**. Current HEAD shows 66 bot diagnostics, not tests-only. Coverage capture in that report used `--no-cov` (80 gate disabled for speed); current gate with `--cov` is red.
- **Native runtime ledger** (`gentle-ai sdd-attempt status --change clean-1-0`): **complete at generation 9**, 9 lifetime attempts, 13244 lifetime lines, `complete: true`, `next_action: complete`, `next_ordinal: 10`. `gentle-ai sdd-status clean-1.0` returns `nextRecommended: sdd-new` with `Active OpenSpec change not found: clean-1.0` because the change lives at `openspec/changes/archive/2026-08-26-clean-1-0/` (archive is audit trail, no `state.yaml` active). Reset is explicitly exceptional and MUST NOT be automatic.

### Root Cause Analysis (CodeGraph-first + config/docs)

**Cluster 1 — Quality gates (ty → prek → coverage triple):**

- **ty root**: `pyproject.toml [tool.ty.terminal] error-on-warning = true` (set by `cycle-5-quality-zero` S1.7: "warnings are fatal, tests/ reached 0 diagnostics via real fixes"). All `warn` level diagnostics become fatal. Overrides downgrade bot files to `warn`:
  ```
  [tool.ty.overrides] bot/cogs/core.py, _slash_compat.py, sentinel.py, tickets.py, utility.py -> unresolved-attribute=warn, unused-ignore-comment=warn
  ticket_lifecycle_flow.py, ticket_repair_service.py, ticket_actions.py, ticket_category_select.py, ticket_panel.py -> possibly-unresolved-reference=warn
  ```
  With `error-on-warning=true`, even downgraded `warn` fails the run. **52 `unused-type-ignore` in bot** are literal dead suppressions (e.g., `bot/cogs/core.py:39,69,84,246,268,330` — `type: ignore[union-attr]`/`no-untyped-call` where narrowing already proves safety). **14 `unresolved-attribute`** are discord.py type gaps (`Interaction[Client]` has no `send`, `None` union `guild.id`, `Group` union `callback`) — real ty errors against the stub, not runtime bugs, but gate-blocking. Tests mirrors the same: `test_tickets_i18n.py:527,576` (`Group.callback` union), `test_s2d1_context_typing_chars.py:87` (`len` on `object`), `test_ocio_permanence.py:140` (`attr-defined` now valid), `test_pr4_tickets_red.py:76` (`no-untyped-def` now dead). **Fix is deletion/real narrowing, not new suppressions.**
- **prek root**: `prek.toml` `ty` hook `entry = "uv run ty check bot/ tests/"` `priority = "type"` runs the same `ty` above on `pre-commit` stage. Because `ty` exits 1, `uvx prek run --all-files` exits 1 → `test_prek_run_all_files_exits_zero` fails. **No prek config bug** — `prek.toml` priorities (`builtin 0, format 10, lint 20, type 30, gga 40, push 50`) and repo lists (`builtin` 4 hooks, `local` ruff/ty/gga/uv-lock/tach) are correct. Fix ty → prek greens automatically.
- **coverage root**: 0.22% miss is **structural, not random**. Uncovered LOC concentrated in **new clean-1.0 surfaces that bypass pytest's default mock path**:
  - `bot/views/setup_modules/welcome.py` 49%, `goodbye.py` 54%, `language.py` 28%, `log.py` 23%, `tickets.py` 69%, `setup_panel.py` 61% — S2a/S2b panel modules tested via targeted panel tests but not via coverage's `bot` import graph when panel not exercised in full suite non-interaction paths.
  - `bot/views/ticket_actions.py` 84%, `ticket_panel.py` 79%, `ticket_category_select.py` 88% — similar.
  - `bot/utils/time.py` 94%, `ticket_helpers.py` 86% — minor.
  - `bot/services/live_catalog.py` 72% — credential-gated live verifier.
  Total `TOTAL 9816 1985 80% FAIL` → need **22 additional covered lines** (`7853` needed vs `7831` covered). Smallest possible fix is **additive tests for one panel module render path** or remove dead code that inflates denominator.

**Cluster 2 — Source-spec slash-only drift:**

- `clean-1.0` S6 (S6A+S6B) migrated ~30 hybrids to pure `app_commands` (verified zero decorators, `bot-core` spec now mandates `ZERO hybrid_command/hybrid_group`, `get_prefix -> []`, help slash-only, `, ` only in `TicketsCog.on_message`). The 13 deltas updated `bot-core`, `setup-panel`, `data-retention`, `operational-config`, etc. to reflect slash-only truth.
- **27 references in 12 specs were NOT in those 13 deltas**, so they still describe the pre-S6 world:
  - `economy-commands`: "hybrid `/rank`, `/leaderboard`, `/daily`, `/coins`"
  - `utility-commands`: "hybrid `/avatar`, `/serverinfo`, `/userinfo`"
  - `sentinel-commands`: every moderation command described as "hybrid ... dual path prefix + slash" (`/warn`, `/unwarn`, `/mute`, `/unmute`, `/kick`, `/tempban`, `/unban`)
  - `ticket-commands`, `unclaim-command`, `setup-wizard`: hybrid `/ticket_panel`, `/create_category`, `/unclaim`, `/setup hybrid`
  - `permission-model`: `is_mod`/`can_check` described as `commands.check + app_commands.check dual path for hybrid commands` (now slash-only, prefix path inert)
  - `slash-locale-translator`, `qa-help-builder`, `i18n-system`, `docs-manual`, `guild-config`: hybrid/locale/describe/prefix references
- **Risk if unpatched**: GGA review will flag future code as violating `specs/*` (e.g., pure slash code "missing" prefix path) when specs are the stale party. Archive sync was correct (deltas merged, no truncation), but source specs need a reconciliation delta — this is `v1-postrelease-zero`'s second slice.

**Cluster 3 — Ledger / verify authority:**

- `sdd-attempt` ledger is **complete and immutable** (generation 9, 13244 lines). Provider CLI (`gentle-ai 2.5.0-rc.2.0`) exposes `sdd-attempt status|begin|finish|reset|repair` and `sdd-verify-validate`. `sdd-status clean-1.0` explicitly says *Active change not found* — dispatcher routing requires `openspec/changes/{name}/` active. Archive path is NOT dispatched. `reset` exists but is documented as exceptional and forbidden to automate. `sdd-verify-validate` validates report bytes offline without ledger mutation.

## Affected Areas

- `pyproject.toml` — `[tool.ty.terminal] error-on-warning=true`, `[tool.ty.rules] unused-ignore-comment=error`, `[[tool.ty.overrides]]` 10 blocks, `[tool.pytest.ini_options] addopts=--cov --cov-fail-under=80`, `filterwarnings=error` — gate policy that makes 80 diagnostics fatal; edits here are policy, not code fix (avoid weakening gate).
- `prek.toml` — `ty` hook `uv run ty check bot/ tests/` `priority=type` on `pre-commit`; `priorities` map; 8 `local` hooks; no bug, but greens only after ty greens.
- `bot/cogs/core.py` — 6+ dead `type: ignore[union-attr]`/`no-untyped-call` (lines 39,69,84,246,268,330) + 5 `unresolved-attribute` (`Interaction.send`, `None.id`) — CodeGraph confirms `on_message` comma listener absent here, only `_noop_prefix` + `on_app_command_error`/`on_command_error`.
- `bot/cogs/_slash_compat.py`, `bot/cogs/sentinel.py`, `bot/cogs/tickets.py`, `bot/cogs/utility.py` — each carries `unused-ignore-comment=warn` override but still fatal via `error-on-warning`; `unresolved-attribute` on `Interaction`/`Group` unions.
- `bot/services/ticket_lifecycle_flow.py`, `bot/services/ticket_repair_service.py`, `bot/views/ticket_actions.py`, `bot/views/ticket_category_select.py`, `bot/views/ticket_panel.py` — `possibly-unresolved-reference=warn` overrides, not currently in the 80 but part of gate surface.
- `tests/test_tickets_i18n.py:527,576` — `Group.callback` unresolved (2 errors); `tests/test_s2d1_context_typing_chars.py:87` — `len` invalid-argument; `tests/test_ocio_permanence.py:140`, `tests/test_pr4_tickets_red.py:76`, `tests/test_ocio_permanence.py:44` — dead `type: ignore` (8 total in tests).
- `bot/views/setup_modules/welcome.py|goodbye.py|language.py|log.py|tickets.py`, `bot/views/setup_panel.py` — coverage gap owners (28–69% vs 94–100% elsewhere); adding render/component paths or pruning dead branches closes 0.22%.
- `bot/utils/checks.py:4,225,229,343,350,361` + `bot/core/i18n.py:277,319` + `bot/cogs/sentinel.py:3` + `bot/bot.py:91,165` — docstring/comment hybrid mentions; `checks.py:229,361` literal `@commands.hybrid_command` examples are the only `hybrid_command` substrings in `bot/` (AST confirms zero decorators).
- `openspec/specs/{economy-commands,utility-commands,docs-manual,slash-locale-translator,qa-help-builder,permission-model,sentinel-commands,ticket-commands,i18n-system,unclaim-command,setup-wizard,guild-config}/spec.md` — 27 stale hybrid/prefix scenarios; `openspec/specs/bot-core/spec.md` is the **correct post-S6 source of truth** (slash-only, `get_prefix -> []`, zero hybrid, comma invariant).
- `openspec/changes/archive/2026-08-26-clean-1-0/` — 9 stacked attempts (S0–S6B), `verify-report.md` `pass_with_warnings` with stale `ty tests-only` claim; `proposal.md`/`design.md`/`tasks.md` correct but archived; no `state.yaml` active means native dispatcher cannot route `sdd-verify` without explicit action.
- `openspec/config.yaml`, `.github/workflows/qa.yml|code-quality.yml` — CI gates that enforce `ty check`, `ruff check`, `tach check`, `uv run pytest --cov-fail-under=80`; any slice must keep these green.
- `.codegraph/` index — local blast radius present for `TicketsCog.on_message`, `TicketRepairService`, `cache_key`, `can_check` — second slice must not touch `TicketsCog.on_message` comma parse (guarded by `tests/test_comma_timer_invariant.py` + `tests/test_close_ticket_dedup.py`).

## Approaches

### 1. Quality-gate restoration (ty → prek → coverage)

Two fix strategies exist; they differ in how much they touch the ty config vs the code/tests:

1. **A — Code-first ty cleanup (recommended)** — Delete every dead `type: ignore` (52 bot + 8 tests), narrow the 14 `unresolved-attribute` with real type fixes (e.g., `interaction.guild` guard before `.id`, `isinstance(interaction, discord.Interaction)` before `.send`, `Group` union `hasattr` guard before `.callback`), fix 4 `invalid-argument` (`len` on `Sized` union) with explicit cast/check. No `pyproject.toml` rule relaxation, no new suppressions, no `error-on-warning` flip. Coverage closed by additive tests exercising one uncovered panel render path (e.g., `setup_modules/language.py` `render`/`components`) — 22+ lines covered, denominator unchanged.
   - Pros: Matches `cycle-5-quality-zero` S1.7 discipline ("real fixes, no new suppressions"); preserves `error-on-warning=true` deterrent; `prek` greens as side effect; smallest policy risk.
   - Cons: Requires touching 9 files across cogs/tests; needs careful discord.py stub reasoning.
   - Effort: Medium (1 slice, ~300–500 lines, <1500).

2. **B — Config-relaxation + bulk suppress** — Downgrade `unused-ignore-comment` from `error` to `warn`, set `error-on-warning=false`, or bulk-add `# type: ignore` to silence 80 diagnostics. Coverage closed by lowering floor to 79 or excluding `views/setup_modules/*` from coverage.
   - Pros: One-line fix, instant green.
   - Cons: Violates locked `cycle-5-quality-zero` S1.7 decision (dashboard-reversible gate that was deliberately made fatal); hides real type debt; floor reduction would need spec/docs drift; future debt re-accumulates silently; `sdd-verify` would falsely PASS stale types.
   - Effort: Low but **rejected** — shrinks the system in the wrong direction (adds a hidden flag state).

### 2. REQUIRED formal clean-1.0 re-verification — two safe paths (both respect "never reset ledger automatically", "never mutate archive copy")

> Evaluation against repo/runtime evidence: `gentle-ai 2.5.0-rc.2.0` provider CLI, archived `clean-1.0` at `openspec/changes/archive/2026-08-26-clean-1-0/` (no active `openspec/changes/clean-1.0/`), ledger `complete:true` generation 9, `sdd-attempt status|reset|repair|begin|finish` and `sdd-verify-validate` available, `sdd-status` dispatcher requires active change.

1. **Approach A — Explicit maintainer-authorized temporary restoration/reopen** — Copy (not move) the archived bundle to a temporary active path `openspec/changes/clean-1.0/` (preserving the archive copy verbatim), run the native `sdd-verify` actor via `gentle-ai sdd-attempt begin --change clean-1.0 --work-unit verify` / `finish` so the dispatcher has attempt authority and line-budget accounting, validate with `sdd-verify-validate --requirements 35 --scenarios 93`, emit `verify-report.md` under the temporary active path, then either (A1) re-archive as a new dated entry with lineage note or (A2) discard the temporary active copy after copying the fresh `verify-report.md` evidence hash into `v1-postrelease-zero`'s report. Archive original never mutated; restoration is explicitly authorized and logged in the proposal/design.
   - Pros: Uses **native dispatcher + attempt ledger authority** (the only provider path that writes a ledger-backed `verify-report.md` under `clean-1.0`); line-budget, generation, and evidence hashes are tracked; satisfies the hard requirement "a formal `sdd-verify` MUST be launched against the prior `clean-1.0` SDD" literally.
   - Cons: Requires **explicit maintainer consent** (archive immutability is `openspec-convention.md` audit-trail rule: "never delete or modify archived changes"); temporarily violates the "active change not found" invariant; needs a documented guard that the archive copy stays byte-identical (`diff -r` proof); `reset` must NOT be used — only `begin` of a new verify work unit on top of generation 9.
   - Effort: Low (orchestrator + docs, no code); **supported by runtime** (`sdd-attempt begin --change` creates a new objective if `state.yaml` exists), but **needs later explicit maintainer decision** to authorize the temporary copy and choose A1 vs A2 archival handling.
   - **What repo evidence says is supported**: `gentle-ai sdd-attempt status|begin|finish|reset|repair` all accept `--change` on an active path; `sdd-status --instructions` for an archived change explicitly tells the native dispatcher to expect `sdd-new` next, so `sdd-verify` on archived `clean-1.0` without an active folder is **not natively dispatched** — restoration is the only way to get native authority.

2. **Approach B — Dedicated active verification-only change (no lineage falsification)** — Keep `clean-1.0` archived untouched. Create a **new active change** (either `v1-postrelease-zero` itself or a thin `clean-1-0-verify` sibling) whose `proposal.md` declares its scope as "re-verify `clean-1.0` generation 9 against HEAD `70db4e3`" and whose `verify-report.md` is produced by running the **same `sdd-verify` actor code** but under the new change's identity, citing `clean-1.0` archive hashes (`proposal.md` 6064 bytes, `tasks.md` 77/77, `verify-report.md` 93/93, `evidence_revision` lineage) as the *objective*, and HEAD's `ty`/`prek`/`coverage`/`ruff`/`tach`/`pytest` outputs as *evidence*. Validation uses `gentle-ai sdd-verify-validate --requirements 35 --scenarios 93` offline (no ledger mutation), or `sdd-attempt begin --change v1-postrelease-zero --work-unit verify-clean-1-0` so the new change's ledger tracks the verification without touching `clean-1.0`'s ledger.
   - Pros: **Zero archive mutation**, preserves audit trail literally; no special authorization needed; works today with evidence already collected (2954 passed, 79.78%, 80 ty, ruff PASS); provider-supported via `sdd-verify-validate` and via `sdd-attempt` under the new change name.
   - Cons: The resulting `verify-report.md` lives under `v1-postrelease-zero` (or `clean-1-0-verify`), **not** under `clean-1.0` — a purist may argue it is not "the `sdd-verify` actor against the archived proposal/spec/design/tasks" but a *proxy* verification. Requires explicit cross-reference (hash-pinned) to prove it evaluated the exact `clean-1.0` artifacts, or the lineage claim is weak.
   - Effort: Low–Medium (same test commands as A, plus cross-reference doc); **fully supported without maintainer exception**, but needs later proposal decision to choose whether the report is filed as `v1-postrelease-zero/verify-report.md` section or as a sibling change.

**Common to both**: No `gentle-ai sdd-attempt reset --change clean-1.0` — ledger at generation 9 is complete; reset is "exceptional and must never be automatic" per this change's own constraints. No `archive`-copy mutation. Both use `uv run pytest` (not naked `pytest`) and `uv run ty check` as gates.

## Recommendation

**Recommended path: Approach B for immediate execution, with Approach A held as maintainer-authorized optional upgrade.**

- **Why B first**: It satisfies the hard workflow requirement ("a formal `sdd-verify` MUST be launched") without requiring an archive-immutability exception, uses only provider-supported primitives (`sdd-verify-validate` + `sdd-attempt` under an active change), and can be executed **before `v1-postrelease-zero` proposal is finalized** to ground planning in true gate state (see Ordering below). The exploration evidence (`70db4e3` HEAD red gates vs archived `pass_with_warnings`) already proves the archived verify is stale; a B-style re-verification will produce a `FAIL` (or `pass_with_warnings` with updated diagnostics) that directly justifies the two slices of `v1-postrelease-zero`.
- **When to upgrade to A**: Only if the maintainer explicitly authorizes a temporary restoration and wants the re-verification report to live under `clean-1.0`'s own ledger (generation 10, work_unit `verify`). That requires a one-line decision in `v1-postrelease-zero` proposal/design: "Maintainer authorizes temporary `archive/2026-08-26-clean-1-0` → `changes/clean-1.0` copy, ledger `begin` at generation 10, post-verify re-archive as `archive/YYYY-MM-DD-clean-1-0-verify/` or discard." Until that line is signed, **do not perform A**.

**Ordering (evidence-prevents-bad-planning):**

1. **Before proposal** (preferred): Run **Approach B re-verification now** against HEAD `70db4e3` (full `uv run pytest` + `uv run ty check` + `uvx prek` + `ruff` evidence capture). File the result as `v1-postrelease-zero` pre-proposal evidence or as `clean-1-0-verify/verify-report.md`. This locks the baseline the proposal will slice against and proves the archived `pass_with_warnings` no longer holds.
2. **Before apply** (minimum): If proposal drafts before re-verification, **block `sdd-apply`** until B (or authorized A) completes and its verdict is recorded in `v1-postrelease-zero` proposal's "Baseline re-verification" section. Applying slices S0/S1 before knowing the true red surface risks mis-budgeting (e.g., proposing 1500 lines when ty alone may need 500).
3. **After S0 / at final verify — rejected**: Re-verifying after S0 conflates S0's fixes with baseline drift; final verify of `v1-postrelease-zero` must verify *its own* deltas, not retroactively validate `clean-1.0`. The formal clean-1.0 re-verification is a **precondition**, not a postcondition.

**Slicing (all slices <1500, stacked-to-main, Comma invariant preserved):**

- **S0 — Quality gates** (ty + prek + coverage, ~350–500 lines, TDD RED→GREEN):
  - `tests/test_pr3_prek_replaces_precommit.py::test_prek_run_all_files_exits_zero` RED stays red until ty greens — this is the harness.
  - Fix 80 `ty` diagnostics by deletion/narrowing (no `error-on-warning` flip).
  - Add minimal coverage tests for `setup_modules` render paths (22+ lines) to lift 79.78% → ≥80%. No `TicketsCog.on_message` diff; guard `tests/test_comma_timer_invariant.py` stays in pre-push.
- **S1 — Slash-only OpenSpec source truth** (~600–900 lines, docs-only + maybe 1 test guard):
  - Convert 27 hybrid/prefix scenarios across 12 specs to MODIFIED deltas that match `bot-core` slash-only truth (`@app_commands.command`, no prefix path, help slash-only). Preserve `close-confirmation` `,` timer spec verbatim. Add AST-level repo-wide hybrid guard if not already owned by S0.
  - No code change; `bot/utils/checks.py` docstring examples updated from `@commands.hybrid_command` to `@app_commands.command` as doc hygiene within this slice (straddles code/docs but <50 lines, keeps CodeGraph blast radius clean).

Both slices are **auto-chain** eligible (`delivery_strategy: auto-chain`, `chain_strategy: stacked-to-main`): S0 targets `master`, S1 targets S0 branch, each slice has clear start/finish, autonomous verify (`uv run pytest --cov-fail-under=80` + `uv run ty check` + `uvx prek run`), and rollback (revert merge commit, DDL none).

## Risks

- **Ty's `error-on-warning` makes bot `warn` fatal — fixing 66 bot diagnostics may expose deeper discord.py stub gaps** (e.g., `Interaction.send` vs `interaction.response.send_message`). Mitigation: narrow with `isinstance`/`hasattr` guards; keep overrides as `warn` (do not escalate to `error`); prove via `uv run ty check` green before touching coverage.
- **Coverage 79.78% is epsilon-close to 80 — flaky-additive test could push it over without real hardening**. Mitigation: require the new tests to exercise *uncovered* `setup_modules` branches (CodeGraph `handle`/`render` paths), not just import the module; assert `TOTAL >=80` as TDD gate.
- **Spec reconciliation (27 references) touches 12 files — easy to miss a hybrid scenario and leave a GGA false-positive**. Mitigation: single `grep -rn hybrid` + `grep -rn "prefix"` over `openspec/specs` as TDD RED in S1, then MODIFIED deltas until grep = 0 (except `bot-core` historical note and `close-confirmation` `,`).
- **Re-verification approach chosen without maintainer sign-off may falsify lineage** (B's proxy report claimed as `clean-1.0`'s own report, or A's temporary copy claimed as original archive). Mitigation: proposal must state chosen approach + lineage handling explicitly; `sdd-verify-validate` hashes and `sdd-attempt status` generation pinned.
- **Comma invariant regression** if S1 doc edits accidentally touch `TicketsCog.on_message`. Mitigation: hard rule "no diff may touch `TicketsCog.on_message`" + `tests/test_comma_timer_invariant.py` in every slice's gate; S0/S1 both list it as required green.
- **Prek single-source violation if `.pre-commit-config.yaml` reappears**. Mitigation: keep `tests/test_pr3_prek_replaces_precommit.py::test_yaml_absent` green; `prek.toml` stays single source.
- **Ledger generation confusion** (9 vs 10) if A is later authorized without documenting generation. Mitigation: record `sdd-attempt status --change clean-1.0` snapshot in `v1-postrelease-zero` design before any `begin`.

## Ready for Proposal

**Yes — with one gated precondition.**

The exploration has determined root causes (ty suppressions → prek fail; epsilon coverage gap in panel modules; 27 stale hybrid references), bounded two slices (<1500 each, comma invariant preserved), and compared the only two safe re-verification paths. The change is deliverable as **2 stacked PRs** under `auto-chain` → `stacked-to-main`.

**What the orchestrator should tell the user / next phase (`sdd-propose`)**:

1. **Decide re-verification authority** (one-line proposal decision): Choose **B (proxy verify under `v1-postrelease-zero`) as default**; if the maintainer wants the report under `clean-1.0`'s own ledger, explicitly authorize **A (temporary restoration → generation 10 → re-archive)**. **Do not ask the user directly in this phase** — surface the two-option trade-off to the orchestrator; the proposal will capture the maintainer's choice.
2. **Schedule the re-verification before `sdd-apply`**: Launch `sdd-verify` (B, or authorized A) **before proposal finalization or at minimum before apply** so `v1-postrelease-zero` slices are planned against the real red baseline (80 ty, 79.78%). The current `70db4e3` evidence is fresh — no need to re-run the full suite unless the proposal changes the baseline.
3. **Carry forward hard constraints**: 1500-line slice budget, `uv run pytest` runner, strict TDD RED→GREEN, `TicketsCog.on_message` `,` invariant untouched, 29 migrations idempotent, `error-on-warning=true` preserved.

**Research recommendation**: **`unselected`** — external `sdd-research` is NOT materially needed. Both clusters are internal (ty config/pytest coverage, OpenSpec spec sync). No external API, SDK, or library lane would change the decision. The only external docs consulted were discord.py stubs and `ty` rule reference, which CodeGraph + `pyproject.toml` already evidence. If the maintainer later requests a lane, the closest would be `discord.py app_commands` migration recipes, but S6 already proved the pattern (CodeGraph `can_check` dual-predicate → single predicate).

**Unresolved product decisions for orchestrator handoff (do not ask user directly)**:

- **Ty gate severity**: Keep `error-on-warning=true` (recommended) or downgrade bot overrides to `ignore`? Keeping `true` preserves zero-debt deterrent; changing it needs a product decision and spec update.
- **Coverage floor**: Hold 80 (and fix via additive tests) vs lower to 79.x vs exclude `setup_modules` from coverage. 80 is spec-locked; lowering needs proposal justification.
- **Docstring hybrid examples**: Normalize `bot/utils/checks.py:229,361` from `@commands.hybrid_command` to `@app_commands.command` as doc hygiene — trivial but needs explicit slot in S1.
- **Repo-wide hybrid guard**: Promote `tests/test_zero_hybrid_guard.py` from S6A-scoped (8 archetypes) to full `bot/cogs/**` AST decorator scan permanently — decide in S1.
- **Re-verification report domicile**: Under `v1-postrelease-zero/verify-report.md` (B) vs new `clean-1.0` generation 10 (A) — maintainer choice.
- **Archive sync vs source-spec reconciliation**: 13 deltas already synced; remaining 27 references need MODIFIED deltas — confirm that `v1-postrelease-zero`'s delta scope is *only* those 12 specs and does not re-touch `bot-core` (which is already truth).
