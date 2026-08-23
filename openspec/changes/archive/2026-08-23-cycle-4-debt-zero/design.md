# Design: Cycle 4 — Debt Zero

## Technical Approach

S1: escalation → `InfractionService` + 5 gates to permission matrix (+ ty fix). S2: C-batch (C2/C11/C4/C6–C14 beyond C5/i18n: task detail in `exploration.md`; REQUIRED input for sdd-tasks). S3: fixes-then-gates ruff/ty; jscpd ratchet. S4: AGENTS V3 + convergence. Red-green TDD for behavior; gates fix-first.

## Architecture Decisions

### D1: `InfractionService.apply_escalation()`

**Choice**:

```python
async def apply_escalation(self, *, guild_id: str, member: discord.Member,
                           moderator: discord.Member, escalation: EscalationAction) -> str
```

Service executes: `match escalation.action` (MUTE → `timeout(duration)`; KICK → `kick()`), `insert_infraction`, `log_moderation_action`, returns a `t()` fragment. Cog keeps validation + embed send.
**Alternatives**: cog-private helper (AGENTS.md violation); per-action strategies (overkill).
**Rationale**: kills ~75 duplicated lines; services importing discord / calling `t()` established (`ticket_repair_service.py`).
**Contract**: only `discord.Forbidden` caught → failed fragment; else propagates. Idempotency via exact-equality thresholds; concurrent-warn race unchanged.

### D2: Decorator migration

Positional swap on warn/unwarn/mute/unmute/kick: `@is_mod()` → `@can_check("moderation.warn"|"moderation.mute"|"moderation.kick")`. Surface: `MissingRole` → `CheckFailure("Missing permission: moderation.X")`; compatible since matrix ⊇ mod-role (`_is_mod_via_matrix`). Dual registration intrinsic to `can_check`.

### D3: C5 `expire_tempbans` reordering

Unban FIRST → `NotFound` ≡ success (manual `/unban` race) → deactivate → count++. Other failures: row stays **active**, `logger.warning`, skip. **No retry flag**: hourly DB-sourced scan re-picks active expired rows — free retry, zero schema change; loop cadence/log unchanged.

### D4: jscpd baseline ratchet

`scripts/jscpd_check.py` runs `npx jscpd@4.0.1 <dir> --reporters json --output <tmpdir>`, parses `statistics.clone.percentage`, compares `reports/jscpd-baseline.json` (`{"bot": f, "tests": f}`). Exit: 0 pass · 2 over-ceiling · 1 infra. prek hook `jscpd-check`: pre-push, files `^(bot/|tests/)`, priority push. CI drops `continue-on-error`, runs the script (same pin). Calibration in S3: ceiling = measured + 0.5pp; lowering = JSON-only commit.

### D5: Ruff hardening

`explicit-preview-rules = true` **changes behavior**: unnamed preview rules under selected families stop firing. Procedure: before/after diff, re-select wanted preview rules, drop stale per-file-ignores. `required-version = "0.15.20"` exact. Per family ASYNC/BLE/G/A/PT011: fix commit then select commit. PT011: `match=` at 8 sites. PLC0415 stays documentation-only advisory (comment in pyproject/docs); NEVER in `select` while PLR/PTH/SLF remain Out-of-Scope.

### D6: ty tightening

S1 fixes `ticket_integrity_flow.py:73` first. `error-on-warning = true` makes every warn diagnostic fatal (override-demoted included), so narrowing precedes gating: shrink `bot/cogs/**` + `tests/**` overrides to per-file entries per scope; enable the gate last in S3.

### D7: prek swap

New id `uv-lock-check`, entry `uv lock --check`, pre-push, priority push. Rename not reuse — semantics changed entirely; local ids are file-local. `ty` untouched = sole type gate.

### D8: i18n key-coverage test

`tests/test_i18n_key_coverage.py`: AST-scans `bot/**` for `t(<guild>, "<literal>")`; asserts each key ∈ es.json ∧ en.json. Dynamic keys via module-level `DYNAMIC_KEY_PATTERNS` regex tuple (`tickets.timer.unit_*`, `ocio.8ball.r\d+`); unused-key check advisory only; failure = one `pytest.fail` listing keys with callsite `file:line`.

### D9: AGENTS.md V3

Insertions: Architecture += `cache_key()` mandate; Database += `IF NOT EXISTS`; Discord.py += `t()` mandatory + `can_check` strict on matrix gates; Anti-patterns += matching ❌ rows. Each rule cites an enforceable pattern; GGA block byte-identical; `— V3` title suffix; lands only once the tree conforms.

### D10: Convergence (E)

After S4 merges: `gga --pr-mode --diff-only f77bf38..HEAD` + suite + prek; max 2 fix rounds; survivors → `residual-debt.md` in the change folder.

## Data Flow

```
/warn: cog(validate) → svc.warn() → escalation? → svc.apply_escalation
       (Discord action → DB insert → log channel) → fragment → cog embed
Expiry (hourly): cog.decay_expiry_loop → svc.expire_tempbans(unban_fn)
       → unban ok → deactivate → log_sentinel_loop
```

## File Changes

| File | Action |
|------|--------|
| `bot/services/infraction_service.py` | Modify — `apply_escalation()`, C5 reorder |
| `bot/cogs/sentinel.py` | Modify — decorator swaps, warn slim-down, C2/C10/C11 |
| `bot/cogs/ticket_integrity_flow.py` | Modify — ty fix |
| `bot/cogs/{ocio,tickets,stellar}.py`, `bot/{bot.py,services/ocio_service.py,services/logging_service.py,utils/embeds.py,core/realtime.py,listeners/voice_listener.py}` | Modify — C4, C6–C13 |
| `bot/locales/{es,en}.json` | Modify — C1/C1b keys |
| `scripts/jscpd_check.py`, `reports/jscpd-baseline.json`, `tests/test_i18n_key_coverage.py` | Create |
| `pyproject.toml`, `prek.toml`, `.github/workflows/code-quality.yml`, `AGENTS.md` | Modify — D4–D7, D9 |
| Tests: `test_checks.py`, `test_pr2_sentinel_red.py`, `test_sentinel_cog.py`, `test_s3d1_guardrails.py`, `test_infraction_service.py`, `integration/test_moderation_flow.py`, `test_bot_probe.py` | Modify — MissingRole→CheckFailure; `is_mod`→`can_check(key)`; deactivate-on-failure → keep-active |

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit | `apply_escalation`: MUTE/KICK ok; Forbidden → fragment; unexpected propagates | mocked db/logging/member |
| Unit | `expire_tempbans`: unban-first; NotFound ≡ success; failure keeps active | db mocks |
| Unit | 5×`can_check(key)` introspection; i18n scanner; jscpd exit codes | checks walk; AST; fake `subprocess.run` |
| Integration | warn→escalation round-trip; real `setup_hook` (C14) | harness |

## Threat Matrix

Applicable boundary (jscpd script spawns npx):

| Boundary | Applicability | Design response | RED tests |
|---|---|---|---|
| Shell/subprocess | Applicable — spawns `npx jscpd@4.0.1` | pinned; tmpdir output; exits 0/1/2; no `shell=True` | argv assertion; bad JSON → 1; over-ceiling → 2 |
| Docs-like / Git selection / Commit·Push·PR state | N/A — script never touches git | — | — |

## Risks

|Risk|Severity|Mitigation|Decision ref|
|---|---|---|---|
|C5 breaks deactivate-even-on-failure tests/specs|High|D3 unban-first order; test-inversion plan|D3+Testing|
|Error-surface churn is_mod→can_check|Med|D2 map covers 5 commands + tests|D2|
|BLE001 narrowing masks catches|Med|Per-site narrowing; reasoned-noqa|D5|
|Ratchet miscalibration|Low|Ceiling=measured+0.5pp|D4|
|Review backlog|Low|Slices <800 lines|Rollout|

## Migration / Rollout

No data migration. Stacked-to-main slices; rollback = revert merge commit. Gates activate after calibration commits; AGENTS V3 only when true-in-tree.

## Open Questions

- [ ] Preview-rule keep-list after `explicit-preview-rules=true` diff (S3, empirical)
- [ ] jscpd +0.5pp margin at calibration
