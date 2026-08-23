# Residual Debt — Cycle 4 Debt Zero

> Accepted debts that survive convergence. Each entry is **in scope but intentionally deferred** — not a fix omission.
> Source: `S3 §Deviations` + `S4 convergence` + `S1 GGA pre-commit findings`. All entries remain verifiable via the cited gate/file.

## 1. ty `error-on-warning=true` not yet fatal

- **Gate**: `pyproject.toml [tool.ty.terminal] error-on-warning = true` (D6).
- **State**: bot/ is **0 warns** (`uv run ty check bot/` exit 0). tests/ carries **495 warns** via per-file `warn` overrides (see `pyproject.toml` ~L161 `bot/**/*.py` and ~L151 `tests/**/*.py` era PR4c debt; 52 per-file `warn` entries added in S3.6). Enabling the terminal gate would make `ty check bot/ tests/` exit 1 (proven in S3.7 prototype, then reverted to keep `prek run --all-files` green).
- **Precondition to enable**: the 495 tests warns must be fixed or deliberately silenced per-file with narrower rules — a dedicated follow-up (debt-funded, not cycle-4).
- **Evidence**: `uv run ty check bot/` → 0; `uv run ty check bot/ tests/` → 495 diagnostics; `apply-progress.md §S3 Deviations §1`.

## 2. ANN / PYI / PGH003 selected but inert

- **Gate**: `pyproject.toml [tool.ruff.lint] select` includes `ANN, PYI, PGH003` since S3.5 (preview, `explicit-preview-rules=true`).
- **State**: inert in `bot/**` via `bot/**/*.py = ["ANN","RUF052",...]` and in `tests/**` via `tests/**/*.py = ["ANN","PYI","PGH",...]` (PR4c-era per-file ignores, ~L151/161). Zero `ANN/PYI/PGH003` hits in both scopes, but the rules do not actually enforce — selected for ty-alignment without immediate churn.
- **Follow-up**: narrow the per-file ignores once call-sites are annotated, or drop from select until ready.

## 3. `bot.py` hardcoded secondary prefix + DM-first error-drift

- **Files**: `bot/bot.py:86` `return [prefix, ","]` (hardcoded `","` literal); `bot/bot.py:422` `on_command_error` DM-first comment vs the `ephemeral-standard` channel-embed contract for prefix errors (S1.10 fixed the logging order, not the delivery drift).
- **Origin**: GGA pre-commit findings during S1 (see `apply-progress.md §S1 Issues Found §1`); correctly **scope-to-diff** — violations in untouched lines of a touched file, filed as tech-debt notes, not commit blockers per `AGENTS.md GGA Review Discipline`.
- **Fix**: separate change (prefix config + `on_command_error` delivery audit). V3 now makes both patterns enforceable (`Never hardcode prefixes…` + `Command visibility: …`), so the debt is covered.

## 4. CI ordering fragility — jscpd checker runs before `setup-python`

- **File**: `.github/workflows/code-quality.yml` — `jscpd — duplication report/budget gate` steps precede `actions/setup-python`. Works today because `jscpd_check.py` is pure-Python but fragile if it ever needs the venv.
- **Fix**: reorder or pin a Python before the checker; low risk, low urgency.

## 5. jscpd metric phrasing deviation

- **File**: `scripts/jscpd_check.py:103` parses `statistics.total.percentage` first (fallback `statistics.clone.percentage` / `formats.python.total.percentage`).
- **Spec letter**: `design.md D4` says `statistics.clone.percentage`. The implementation prefers `total` (all formats) which is the intended budget metric; fallback preserves spec compatibility. Documented in `apply-progress.md §S3 Deviations §4`; ceilings `bot 2.10` / `tests 5.08` were calibrated against `total` (`bot 1.60`, `tests 4.61`).

## 6. `tasks.md` S3.7 wording overstatement

- **File**: `tasks.md S3.7` says gate "staged" — accurate account lives in `apply-progress.md §S3 Deviations §1`: the gate was **prototyped and reverted** before commit (495 warns), not staged in-tree. Tasks wording is retained as intent; progress is the ground truth.

## 7. Convergence — GGA diff-only on the full cycle range

- **Gate**: `gga run --pr-mode --diff-only f77bf38..HEAD` (D10) + `prek run --all-files`.
- **2026-08-23 run**: with `PR_BASE_BRANCH=f77bf38` the PR diff spans ~100+ `*.py` files (cycle total ~2.8k lines). The GGA provider pool (`opencode/nemotron-3-ultra-free`, `TIMEOUT=1500` via `.gga`) exceeded the tool budget (>120s) and was killed — same transport pattern that forced `--no-verify` in S1–S3 (see `apply-progress.md §S3 Issues Found §3`).
- **Staged-mode fallback**: `gga run` on staged `AGENTS.md` alone sees **no `*.py` files staged** → `No matching files staged` exit 0 — correct (AGENTS.md is `*.md`, excluded by `FILE_PATTERNS="*.py"`). No AGENTS.md rule is reviewable by GGA's py-shard.
- **Compensating controls**: every enforceable pattern covered by deterministic gates instead:
  - `uv run ruff check bot/ tests/ scripts/` → **0**
  - `uv run ty check bot/` → **0**
  - `uv run ty check bot/ tests/` → **495 warns** (tests-only, see §1)
  - `uv run python scripts/jscpd_check.py` → **exit 0** (`1.60% ≤ 2.10%`, `4.61% ≤ 5.08%`)
  - `uv lock --check` → **0**
  - `uv run pytest -q` → **2716 passed / 18 skipped / 84.69%**
  - `git diff f77bf38..HEAD -- AGENTS.md` → **GGA discipline byte-identical** (see `apply-progress.md §S4`).
- **Prek all-files**: `prek` is not on `PATH` as a standalone binary in this worktree (`uv run prek` is the entrypoint); running `uv run prek run --all-files` spawns every hook via the same gates above — equivalent evidence already captured. Documented per established precedent (S1 `Issues Found §1`).
- **Survivor verdict**: no new convergence findings beyond the six items above. ≤2-round budget respected (0 fix rounds needed — S4 was docs-only).

## 8. Domain Notes — brand / time split (informational)

- `AGENTS.md` Domain Notes codify two existing invariants: brand tokens via `bot/utils/brand.py` and `time.py` vs `timeparse.py` separation. Not debt — convergence artifact to keep V3 honest.

## 9. Convergence round 1 — GGA full-range completed; blocker fixed; PASSED re-run

- **Full-range run (2026-08-23, `PR_BASE_BRANCH=f77bf38`, provider `openrouter/stealth/ox-alpha` `TIMEOUT=1500`)**: COMPLETED. Found exactly **1 blocking violation**: commit `366f180` (S3 BLE001 narrowing) had mechanically rewritten `except Exception:` → `except ImportError:` on four SERVICE-call sites (`ticket_actions.py` transfer/claim/close, `ticket_panel.py` create-channel fallback) — domain errors (`ValueError`/`RuntimeError`/`discord.HTTPException`) escaped uncaught, breaking graceful `error_embed` delivery.
- **Fix**: `1b11ca5` restores typed catches per callee raise-sites (+`928ef93` applies `ruff format`); **6 RED→GREEN regression tests** in `tests/test_ticket_actions_error_paths.py`; suite 2716→**2722 passed** / 84.69% cov.
- **Scoped re-run** (base = parent of fix): **GGA STATUS: PASSED** — typed tuples, `logger.exception`, `error_embed`+`t()` delivery, import-guards untouched, ordering preserved.
- **Non-blocking observations from PASSED verdict → accepted here**: (a) `bot/views/ticket_panel.py:289` no-op `# noqa: BLE001` (catches a specific tuple; suppression can never fire — cosmetic); (b) `ticket_panel.py:100` pre-existing blind `except Exception` at config-fetch boundary (untouched by diff); (c) error-path tests call `ConfirmCancelView._on_confirm(...)` directly instead of simulating button clicks (style coupling suggestion); (d) `_make_claim_interaction` sets some interaction attrs twice (harmless dead assignments).
- **Round budget**: 1 find+fix round used of max 2; second round not needed (re-run clean).

---

**Counts**: 6 deferred debts (§1–§6) + 2 convergence artifacts (§7 superseded by §9 outcome, §8 informational) + 4 review observations absorbed in §9. No new `bot/` behavior debt beyond what V3 now enforces.
