# Archive Report — cycle-4-debt-zero

**Archived**: 2026-08-23
**Change**: cycle-4-debt-zero
**Head at archive**: `928ef935beaaa815bd80285569ab56b1d2a70609`
**Base**: `f77bf38` (62 commits in range; 20 cycle-4 commits `40da923..928ef93`)
**Artifact store**: OpenSpec (`openspec/changes/archive/2026-08-23-cycle-4-debt-zero/`)

---

## Final State (Terminal Authority)

Per `verify-report.md` Round 2 (evidence_revision `sha256:cffa3c7cdcabae8faaf5acf3b5ee3119e2785a95552f958a1430f918bc27424d`), verified at HEAD `928ef93` after remediation:

| Metric | Final Value |
|--------|-------------|
| Verdict | `pass_with_warnings` |
| Requirements | 33/33 |
| Scenarios | 94/94 (93 runtime-compliant; 1 accepted ty residual) |
| Tests | 2722 passed, 18 skipped, 0 failed |
| Coverage | 84.89% (threshold 75%; cycle baseline 84.33% satisfied) |
| Assertion quality | 0 CRITICAL, 0 blocking tautologies |
| Blockers | 0 |
| Critical findings | 0 |
| Warnings | 5 (non-blocking) + 2 suggestions |

**Test run**: `uv run pytest -q --cov=bot` → exit 0, `sha256:b7cd96de86536244d38867efe2e4eeff1b32d24a8069cfc69e3d5e74a4377ee4`.
**Build run**: `uv run ty check bot/` → exit 0, `sha256:82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18`.
**Round 2 gate matrix**: ruff check (0), ruff format --check (247 files), ty bot (0), jscpd checker (0; bot 1.60% ≤ 2.10%, tests 4.68% ≤ 5.08%), uv lock --check (0), tach check (0), GGA block byte-identical (0), prek all-files (0) — all green.

### Convergence E (CLOSED)

Full-range GGA (`f77bf38..HEAD`) found 1 blocking violation: commit `366f180` mechanically rewrote `except Exception:` → `except ImportError:` on four ticket service call-sites, breaking graceful `error_embed` delivery for `ValueError`/`RuntimeError`/`discord.HTTPException`. Fixed in `1b11ca5` (restored typed catches per callee raise-sites) + `928ef93` (ruff format follow-up). Six RED→GREEN regression tests added in `tests/test_ticket_actions_error_paths.py` (2716→2722 passed). Scoped re-run: GGA STATUS: PASSED; round budget 1/2 used.

### Residual debt (accepted, deferred)

6 deferred debts (§1–§6) + 2 convergence artifacts (§7 superseded by §9, §8 informational) + 4 review observations absorbed in §9. See `residual-debt.md` in the archived folder for the full ledger. Headline items: ty `error-on-warning=true` gate deferred (495 test warns), ANN/PYI/PGH003 inert, `bot.py` prefix+DM drift, CI jscpd ordering, jscpd metric phrasing, S3.7 wording. None are CRITICAL; all are debt-funded follow-ups, not fix omissions.

---

## Goal

Close cycle-4 debt with zero regressions: `tickets.timer.*` raw-key leak, 5 `@is_mod()`→`@can_check()` swaps, escalation dedup into `InfractionService.apply_escalation()`, i18n key coverage, expired-tempban unban-first semantics, kick/ban permanence, ruff/ty strictness, jscpd baseline ratchet, AGENTS.md V3, and GGA diff-only convergence.

## Instructions

- **execution_mode**: auto
- **artifact_store**: openspec
- **delivery_strategy**: auto-chain / stacked-to-main
- TDD red-green for behavior items; config tasks exempt with state-verification commands.

## Accomplished

- ✅ S1 (9/9): `apply_escalation` service contract + 5 matrix gates + ty fix — `40da923`, `38a599f`, `487b802`
- ✅ S2 (17/17): i18n keys + C5 unban-first + C2/C11 permanence/drift + C4 logging + C6–C14 hygiene — `b83c7df`, `c0b5d1d`, `e1fbbf6`, `6277c85`
- ✅ S3 (14/14): ruff/ty fixes→gates + jscpd ratchet + C14 bot probe — `4f25aa5`, `e4591f1`, `b11b850`, `366f180`, `d7fdd19`, `2068720`, `d1805a0`
- ✅ S4 (5/5): AGENTS V3 + E convergence + residual ledger — `6eca65d`, `1b11ca5`, `928ef93` (+ `.gga` chores `53f3c08`, `0f6656c`)
- ✅ X.1 cross-slice regression: full suite green, prek all-files clean, GGA diff-only PASSED
- ✅ Task Completion Gate: 46/46 tasks `[x]`, 0 unchecked — PASS
- ✅ 13 delta specs synced to main specs (1 new capability + 12 modified)
- ✅ Change folder moved to archive with mechanical `git mv` + `diff -r` byte-identity readback

## Specs Synced (13)

| Domain | Action | Details |
|--------|--------|---------|
| duplication-budget | Created (new capability) | Mechanical copy of delta as full spec (6 requirements: baseline file, checker exit contract, pre-push hook, CI gate, calibration, lowering protocol) |
| sentinel-commands | MODIFIED ×8 in-place | Warn/Unwarn/Mute/Unmute/Kick/Ban (top section) + Tempban/Unban (voice-moderation delta block); matrix-gated, dual-path, permanent final results, typed UnbanTarget, no-drift expires_at |
| infraction-service | ADDED ×1 + MODIFIED ×1 in-place | ADDED `Apply escalation service method` (4 scenarios); MODIFIED `Expired tempban is unbanned` (unban-first, NotFound≡success, retry via DB-sourced scan) |
| ephemeral-standard | MODIFIED ×1 in-place | `Mod action commands permanent standard` (two-phase visibility; kick/ban final result permanent, dialog ephemeral) |
| close-confirmation | ADDED ×1 | `Visibility reconciliation — ephemeral dialog, durable outcome` (2 scenarios) |
| confirm-dialog | ADDED ×1 | `Ephemeral dialog, permanent outcome` (2 scenarios) |
| i18n-system | ADDED ×3 | `Translation key coverage test`, `Ticket timer locale keys`, `Eight-ball embed title key` (7 scenarios) |
| ocio-commands | MODIFIED ×1 in-place | `8ball command` (localized embed_title, ephemeral, no DB) |
| logging-service | ADDED ×2 | `Zero-count digest suppression`, `Global error handlers log exceptions` (4 scenarios) |
| pyproject-toml-qa-config | MODIFIED ×2 in-place | `Ruff configuration present` (preview, required-version, ASYNC/BLE/G/A/PT011); `ty configuration present` (terminal error-on-warning, narrowing precedes gating) |
| pre-commit-config-file | REMOVED ×1 + ADDED ×2 + MODIFIED ×1 in-place | REMOVED `Pre-push stage runs uv check and tach` (→ uv lock check); ADDED `Pre-push stage runs uv lock check and tach`, `jscpd-check pre-push hook`; MODIFIED `Hook priorities and ordering` |
| ci-workflow-file | ADDED ×1 | `Duplication gate enforced in CI` (continue-on-error removed, baseline enforced) |
| docs-manual | ADDED ×1 | `AGENTS.md V3 rule slots` (cache_key, IF NOT EXISTS, t(), can_check; GGA byte-identical) |

**Totals**: 1 new spec + 12 updated specs; 11 ADDED requirements + 14 MODIFIED requirements + 1 REMOVED requirement across the 13 deltas.

## Archive Contents

- proposal.md ✅
- design.md ✅
- tasks.md ✅ (46/46 tasks complete; 0 unchecked)
- apply-progress.md ✅
- verify-report.md ✅ (Round 2 PASS WITH WARNINGS, 0 critical)
- residual-debt.md ✅ (§1–§9 survivor ledger)
- exploration.md ✅
- specs/ ✅ (13 delta specs)
- archive-report.md ✅ (this file)

## Source of Truth Updated

The following main specs now reflect the new behavior:
- `openspec/specs/duplication-budget/spec.md` (new)
- `openspec/specs/{sentinel-commands,infraction-service,ephemeral-standard,close-confirmation,confirm-dialog,i18n-system,ocio-commands,logging-service,pyproject-toml-qa-config,pre-commit-config-file,ci-workflow-file,docs-manual}/spec.md`

## Mechanical Copy Readback

- `duplication-budget` main spec: `cp` + `diff -r` (source vs temp) → empty diff (byte-identical). ✅
- Archive move: `git mv` + `diff -r` (pre-move snapshot vs archived tree) → empty diff (archive-report additive-only, excluded). ✅

---

## Next Steps

- **Cycle complete**. Backlog topics for the next session: (1) fund the 495 test-warning cleanup to enable the fatal ty `error-on-warning=true` gate (residual-debt §1); (2) narrow the inert ANN/PYI/PGH003 per-file ignores or drop from `select` until ready (§2); (3) separate change for `bot.py` hardcoded secondary prefix + `on_command_error` DM-first delivery drift (§3); (4) CI jscpd-before-setup-python ordering hardening (§4).

## Key Learnings

1. Mechanical archive copy MUST use shell `cp -R`/`git mv` with `diff -r` readback, never model Read/Write, to guarantee byte-identity of the audit trail.
2. MODIFIED delta requirements are replaced in-place in the main spec; only ADDED requirements append a `<!-- BEGIN/END DELTA -->` marker block per repo convention.
3. The Task Completion Gate requires the persisted tasks artifact to show 0 unchecked `[ ]` before any spec sync or archive move — internal todo state is insufficient.
4. GGA convergence on a large diff range can find mechanical-but-real blockers (BLE001 narrowing that broke typed error handling) even after deterministic gates pass.
