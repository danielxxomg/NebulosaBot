# Design: tests-slim

## Technical Approach

Tests-only from `2bb4e89` (184/61,622/3005/80.50%). S1-S3 parametrize, S4 deletes only with `uv run pytest --cov=bot --cov-fail-under=80 --randomly-seed=42` per batch. No `bot/`; 7 KEEP untouched/green; `filterwarnings=error`+seed 42. Stacked `test/tests-slim-s1`..`s4`; revert `git revert`.

Covers S1-S4 and `test-suite-governance` (4 req / 8 scenarios).

## Architecture Decisions

### D1 — `conftest.py` hoist

| Option | Tradeoff | Decision |
|---|---|---|
| Shared `load_test_locales(tmp_path, es, en?, guild_langs)` matrices stay per-file | Minimal churn, keeps int/str guild ids | **Chosen** |
| Centralize matrices | Forces unification, noisy diffs | Rejected |
| Autowire as autouse | Breaks `_isolate_i18n_state` layering | Rejected |
| Factory direct import vs alias shim | Direct cleaner; alias noise | **Direct import; alias only for sig shim** |

`conftest.py` imports only `bot.core.i18n`+stdlib. `_isolate_i18n_state` stays outermost; hoisted fixtures `yield`. Audit: 6 greetings + `ticket_helpers:244` have divergent sigs → adapt to canonical `make_member(*, roles, admin, member_id, display_name)` at :260; channel scaffolding stays local.

### D2 — Parametrize IDs

| Option | Tradeoff | Decision |
|---|---|---|
| `id="es"/"en"` | `-k es` readable, seed-stable | **Chosen** |
| Auto ids | Numeric, unsearchable | Rejected |

Reuses `param(ES,"ES",id="es")` pattern; S3 solos use `id="welcome-disabled"` style.

### D3 — S4 ordering + proof

| Option | Tradeoff | Decision |
|---|---|---|
| Batch A 3 proven first, then 12 conditional | Isolates win/proof load | **Chosen** |
| All 15 together | Dip hides culprit | Rejected |

Batch A (~560 ln): `8ball_cooldown`→`test_8ball_command_ephemeral`, `greetings_red`→`can("greeting.manage")`, `tickets_red`→`CheckFailure`. 12 (`No twin`/`Needs map`/`Partial`): commit needs `Proof:` (a) twin path+assertion or (b) `rg`+live test; reviewer re-runs `rg`. Fail → survives.

### D4 — Coverage

| Option | Tradeoff | Decision |
|---|---|---|
| `uv run pytest --cov=bot --cov-fail-under=80 -q --randomly-seed=42` per batch+slice | Matches `pyproject.toml addopts` | **Chosen** |
| Strict 80.50 fail-under | Rounding brittle | Gate 80.50, fail-under 80 |

Revert: `git revert <commit>` + re-measure `uv run pytest --cov=bot -q`.

### D5 — PR slicing

| Option | Tradeoff | Decision |
|---|---|---|
| 4 stacked `test/tests-slim-s*` → master chain | Regex-valid `test/`, type:chore | **Chosen** |
| `feat/` | Implies prod | Rejected |

One slice = one PR = work-unit commits + ledger. S1→master, S2→S1, etc.

### D6 — Economy twins (S3)

| Option | Tradeoff | Decision |
|---|---|---|
| Parametrize `stellar_cog`+`stellar_i18n` overlap, keep `economy_service` | Service stays truth for math | **Chosen** |
| Delete service tests | Loses edge cases | Rejected |

Already parametrized in `stellar_i18n:261`; S3 collapses dup, no file delete.

### D7 — Risk

| Option | Tradeoff | Decision |
|---|---|---|
| Flake → check `_isolate_i18n_state` ordering | Proven locale-bleed cause | **Chosen** |
| Cov dip → revert batch only | Isolates blast radius | **Chosen** |

## Data Flow

```
conftest ─► *_i18n.py / greeting_*.py ─► pytest --seed 42 --cov=bot ─► cov≥80.50%
                            └─► KEEP (7) green
```

## File Changes

| File | Action | Description |
|---|---|---|
| `tests/conftest.py` | Modify | Add `load_test_locales`/`build_nested`/`swap_suffix` |
| `tests/test_*i18n.py` (5) | Modify | Use shared helpers |
| `tests/test_greeting_*.py` (6)+`ticket_helpers.py` | Modify | Use `make_member` |
| `tests/test_greeting_service.py` | Modify | Collapse `TestDispatchWelcome` 12+4 into `parametrize id=` |
| `tests/test_pr3_8ball_cooldown_red.py` etc. (3) | Delete | Batch A |
| `tests/test_pr3_*`/`pr4a/b/c*` (12) | Delete iff proven | Else survive |
| KEEP 7 | Untouched | `comma_timer`/`zero_hybrid`/`i18n_key_coverage`/`s3d1_guardrails`/`ops_observability`/`economy_math`/`rank_renderer_wiring` |

## Interfaces / Contracts

```python
def build_nested_locale(m: dict[str,str]) -> dict: ...
def swap_suffix(m: dict[str,str], sfx: str) -> dict: ...
def load_test_locales(tmp_path: Path, es: dict, en: dict|None=None,
                      guild_langs: dict[str,str]|None=None) -> None: ...
def make_member(*, roles=(), admin=False, member_id=111222333, display_name="TestUser") -> MagicMock: ...
```

Every `parametrize` needs `id="es"/"en"`. Ledger: `files: A→B, lines: X→Y, collected: N→M, cov: 80.50%→Z%, seed 42`.

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit | Isolation + factory sigs | `--randomly-seed=42` + random |
| Integration | Same embeds/markers | KEEP suite + cov gate |
| E2E | — | `ty`/`ruff`/`vulture` 0 |

Gates per slice: green + cov≥80.50% + ty/ruff/vulture 0 + ledger.

## Threat Matrix

N/A — no routing/shell/subprocess/VCS/process boundary. Tests-only.

## Migration / Rollout

Stacked `test/tests-slim-s1`..`s4` (S1→master). S1-S3 parametrize, S4 deletes last; never squash. Ledger in PR body.

### Honest Arithmetic

184/61,622. Proven 3→181 files. All 15 (2,618)→169/~58,444. S1-S3 ~1,500-2,000. Max ~4,618→~57,004/169 — still >53-55k/145-160. 12 survive→181/~59,500. **Conclusion**: 145-160 unreachable here; achievable **169-181 / ~57-60k**. Target aspirational; S4 gated proven-only; follow-up needs more candidates.

### Spec Scenarios (8/8)

KEEP green/untouched; parametrization green+cov/isolation+ledger (D4+D7+ledger+seed 42); deletion twin/ without-proof (D3 survive+revert); ledger present/target (ledger contract; 169-181 gated).

## Open Questions

- [ ] `test_utility_i18n.py` single-locale keeps `en=None` path — confirm no new EN needed.
- [ ] `test_core_cog.py:37 _load_i18n` out of S1 scope — leave untouched.
