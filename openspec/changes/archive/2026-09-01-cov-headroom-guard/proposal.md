# Proposal: cov-headroom-guard

## Intent
Lift headroom 0.03pp → ~0.3pp (80.53% → ≥80.8%) at `581c37f` 2953/19 (#5018/#5020). Two-tier gate at risk — config 80 (`pyproject.toml:60`, `Makefile:24/27`, `ci.yml:59`) and spec 80.50 (`ops-observability:133,146`, `test-suite-governance:48`). Guard slice before next feature.

## Scope

### In Scope
- Tests-only covering lows `bot/cogs/core.py` 54.8% and `bot/bot.py` 77.6% (#5018)
- `uv run pytest` green at ≥80.8%
- Keep `test-suite-governance`: KEEP 7 untouched, parametrization style, NO deletions (D3 N/A)

### Out of Scope
- Prod code fixes (bug found → finding only), `AGENTS.md` (separate edit), P3 greetings/dashboard/refactors/deps

## Capabilities

### New Capabilities
- None

### Modified Capabilities
- None — floor unchanged; ledger is commit metadata, not delta

## Approach
Single slice 150–250 ln vs 1500. Mocked branches, no `sys.modules`, no `or True`, `io.BytesIO`, seed 42:
- `bot.py`: `_setup_retention` (OperationalConfig + disabled cron unschedule), `_start_realtime` degraded, `get_context`, `on_app/command_error` (MissingPermissions/CheckFailure/Cooldown + crash fallback), `_validate_single_panel` (missing channel/msg, re-deploy)
- `core.py`: `_is_interaction`/`_guild_id_from_source`/`_resolve_prefix`, `_InteractionCtx.send/defer`, `_send_via`, `ping/status/help` shim vs slash, `_build_cog_help_embed` groups

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `tests/test_*core*.py`, `tests/test_bot*.py` | New | Branch tests |
| `tests/conftest.py` | Modified | If helper needed |
| `bot/cogs/core.py`, `bot/bot.py` | KEEP | Untouched |
| `openspec/specs/*` | KEEP | No delta |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Mock leak / order flake | Med | Keep `_isolate_i18n_state`, seed 42+random |
| Tautological assert | Low | Assert embed/call args |
| Prod bug surfaced | Low | Record, separate slice |

## Rollback Plan
`git revert <sha>` — tests-only, no DDL.

## Dependencies
Baseline `581c37f` 2953/19 80.53% `ty`/`ruff`/`vulture` 0. Evidence #5020/#5018/#5021.

## Success Criteria
- [ ] `uv run pytest --cov --cov-fail-under=80 --randomly-seed=42 -q` green (+ random)
- [ ] Coverage ≥80.8% (≥0.3pp over spec)
- [ ] KEEP green, `ty`/`ruff`/`vulture` 0, hygiene holds
- [ ] No prod diff; `AGENTS.md` not staged

## Review Workload Forecast

| Slice | Forecast | vs1500 | Chained | Gates |
|-------|----------|--------|---------|-------|
| S1 | 150–250 ln | 10–17% | No | seed42+random+ty0/ruff0/vulture0+cov≥80.8 |

Decision needed before apply: No. Chained PRs recommended: No. 400-line budget risk: Low.

## Gates per Slice
Suite green + `ty`/`ruff`/`vulture` 0 + cov≥80.8 + seed42+random + KEEP + no prod diff.

## Target Census

| File | Uncovered | Target |
|------|-----------|--------|
| `bot/bot.py:216,224` | cairosvg probe | both branches |
| `bot/bot.py:306–385` | `_setup_retention` | OperationalConfig + disabled |
| `bot/bot.py:498–654` | `on_app/command_error` | deny/cooldown paths |
| `bot/bot.py:726–821` | `_validate_single_panel` | missing channel/msg |
| `core.py:32,36–42,72–105` | helpers + `_InteractionCtx` | guild/prefix/send/defer |
| `core.py:231–399` | `_send_via` + `ping/status/help` | shim vs slash |
