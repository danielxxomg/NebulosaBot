# Proposal: Cycle 4 — Debt Zero

## Intent

Close cycle-4 debt with zero regressions; `tickets.timer.*` leaks raw keys to users today; green suite = safe window.

## Scope

### In Scope
- **A**: 5 `@is_mod()`→`@can_check()` swaps; escalation dedup into `InfractionService.apply_escalation()`; ty fix
- **C**: C1–C14 batch per exploration.md (headline: i18n keys, C5 retry gap, C2/C11 permanence+drift, C4 logging)
- **B**: jscpd CI-advisory → blocking baseline-ratchet
- **F**: prek `uv lock --check`; ruff ASYNC/BLE/G/A/PT011 blocking post-fix (~44 hits); ty error-on-warning
- **D**: AGENTS.md V2→V3: cache_key, IF NOT EXISTS, t(), can_check strict; GGA verbatim
- **E**: gga diff-only f77bf38..HEAD + suite + prek; ≤2 rounds → debt report

### Out of Scope
Dashboard QA; Betterleaks; OSV; Semgrep; mutmut; Vulture; zizmor; PLR/PTH/SLF. Lock/unlock/modlogs + locales untouched.

## Capabilities

### New Capabilities
- `duplication-budget`: baseline JSON; prek + CI fail above it; lowering protocol

### Modified Capabilities
- `sentinel-commands`: warn/unwarn/mute/unmute/kick matrix-gated; kick/ban permanent; typed `UnbanTarget`; `expires_at` fixed
- `infraction-service`: ADDED `apply_escalation()`; MODIFIED expired-tempban semantics (C5)
- `ephemeral-standard`: kick/ban permanence enforced
- `close-confirmation`, `confirm-dialog`: dialog=ephemeral, result=permanent
- `i18n-system`: key-coverage test + dynamic-key allowlist
- `ocio-commands`: 8ball `embed_title` required
- `logging-service`: suppress zero-count digest
- `pyproject-toml-qa-config`: ruff/ty strictness
- `pre-commit-config-file`: `uv lock --check` swap; jscpd hook
- `ci-workflow-file`: jscpd enforces baseline
- `docs-manual`: AGENTS.md V3 rule slots

## Delivery Slices

Stacked-to-main, work-unit commits.

- **S1** (~420 ln): A + ty fix; escalation extraction
- **S2** (~680 ln): C batch (C5+delta, C1/C1b/C1c, C2/C11, C4, C6–C13, C14*); C14 overflows→S3
- **S3** (~550 ln): F+B — fixes before gates
- **S4** (~160 ln): D + E convergence + residual report

TDD red-green for behavior items; config exempt.

## Affected Areas

- Modified: `bot/cogs/sentinel.py`, `bot/services/infraction_service.py`, `bot/cogs/ticket_integrity_flow.py`, `bot/bot.py`, cogs `ocio/stellar/tickets`, services `ocio_service/logging_service`, `utils/embeds.py`, `core/realtime.py`, `listeners/voice_listener.py`
- New: `bot/locales/{es,en}.json` keys, key-coverage test, `reports/jscpd-baseline.json`, `scripts/jscpd_check.py`
- Config/docs/tests: `pyproject.toml`, `prek.toml`, CI workflow, `AGENTS.md`, `tests/test_bot_probe.py`

## Risks

- **C5 breaks deactivate-even-on-failure tests/specs** (High) — tests first + delta
- **Error-surface churn** (Med) — migrate check/flow tests; matrix ⊇ mod-role
- **BLE001 narrowing masks catches** (Med) — per-site narrowing; reasoned noqa
- **Ratchet miscalibration** (Low) — ceiling=measured+margin in S3
- **Review backlog** (Low) — slices <800 lines

## Open Questions (defaults marked)

1. **C5**: deactivate post-success-unban; `NotFound`≡success; auto-retry
2. **jscpd**: both — baseline JSON (prek) + CI fail-above-baseline
3. **PT entry**: PT011 only; PT018 deferred

## Rollback

Stacked PRs; revert per merge commit; specs untouched until archive.

## Dependencies

Node/npx (`jscpd@4.0.1`); no new Python deps.

## Success Criteria

- [ ] Suite green; coverage ≥84.33%; no user-reachable raw i18n keys
- [ ] 5 commands matrix-gated; one escalation path; ASYNC/BLE/G/A/PT011 zero-hit; ty fatal
- [ ] jscpd ratchet active (prek + CI); AGENTS.md V3 true-in-tree, GGA byte-identical; gga diff-only clean f77bf38..HEAD
