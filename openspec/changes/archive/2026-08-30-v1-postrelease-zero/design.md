# Design: v1-postrelease-zero — Restore v1.0.0 Gates and Slash-Only Truth

## Technical Approach

Two slices <1500 (`auto-chain`→`stacked-to-main`) restore 70db4e3. S0: ty 80→0, prek green, 79.78%→≥80% via additive `setup_modules` tests. S1: 12 specs (27 hybrid/prefix)→slash-only + `checks.py:229,361` swap, AST 0. Proxy `sdd-verify` of `archive/2026-08-26-clean-1-0` (gen9, 35 req/93 scen, 6064 B) is hard pre-apply gate; archive/ledger untouched. Preserve `error-on-warning=true`, 80, 29 migrations, `,` invariant.

```
70db4e3 (ty80/prek fail/cov79.78) ─▶ S0 ty0+prek green+cov≥80 ─▶ PR S0→main
                                  ─▶ S1 27→0+AST0 ────────────▶ PR S1→S0
                                  ─▶ proxy validate 35/93 blocks apply
```

## Architecture Decisions

| D# | Decision | Options | Tradeoff | Choice & Rationale |
|----|----------|---------|----------|-------------------|
| D1 | ty hygiene | A delete+narrow / B relax gate | B hides debt, violates S1.7 | **A**: delete 52+8 ignores, narrow 14+4 via `isinstance`/`hasattr`/guarded `guild.id`/`Group.callback`/`len(Sized)`. Keeps deterrent |
| D2 | 10 overrides | remove vs keep | Remove re-exposes `possibly-unres` | **Keep** `warn` (ticket flows+5 cogs). Still fatal; not in 80 |
| D3 | Coverage | A additive / B lower 80 | B shrinks denominator | **A**: cover 22 lines via `handle`/`render`; denominator unchanged |
| D4 | S1 docstring | only 229,361 vs repo-wide | Full touches i18n/bot history | **Only 229,361** + sentinel:3/bot:91 |
| D5 | Hybrid guard | grep vs AST | grep false+ on docstring | **AST** decorator scan 0; `test_zero_hybrid_guard.py` repo-wide |
| D6 | Proxy verify | A restore→gen10 vs B proxy | A needs mutation exception | **B**: `verify-report.md` hash-pinned; `validate --requirements 35 --scenarios 93`. A only if signed |
| D7 | Comma | forbid vs allow `on_message` | Allow risks `close-confirmation` | **Forbid** diff to `TicketsCog.on_message` |

## Data Flow

```
S0: ty check (error-on-warning) ─▶ prek ty hook (type, pre-commit) ─▶ green when ty 0
S0: pytest --cov-fail-under=80 ─▶ setup_modules/* handle/render_async/components (22 lines)
S1: specs/12 deltas ─▶ checks.py docstring ─▶ AST bot/cogs/**/*.py =0
archive/clean-1-0 (6064B f5ba5f…, 93/93) ─▶ sdd-verify-validate ─▶ v1-postrelease-zero/verify-report.md
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `pyproject.toml` | Verify | Keep `error-on-warning=true`, `unused-ignore=error`, 10 overrides `warn`, `--cov-fail-under=80` |
| `prek.toml` | Verify | Keep `ty` hook `uv run ty check bot/ tests/` type priority |
| `bot/cogs/core.py` | Modify | Delete 6 ignores 39,69,84,246,268,330; fix `send`/`guild.id` |
| `bot/cogs/stellar.py` | Modify | Delete 8 ignores 54,77-78,137-138,188,259-260 |
| `bot/cogs/sentinel.py` | Modify | Delete 14 ignores 93,103,108,861-905,937-981 |
| `bot/cogs/utility.py` | Modify | Delete ignores 48,50-51,92,94,97,165,194,232,234 |
| `bot/cogs/ocio.py` | Modify | Delete 11 ignores 40,69,80,85,98,107,123,131,136,146,153 |
| `bot/cogs/tickets.py` | Modify | Delete 2 ignores 76,79; `Group.callback` hasattr |
| `bot/utils/checks.py` | Modify | `hybrid`→`slash`; 229,361 `hybrid_command`→`app_commands.command` |
| `bot/cogs/sentinel.py:3` `bot/bot.py:91` | Modify | `hybrid`→`slash` |
| `bot/views/setup_modules/language.py` | Covered | 46 lines 71-121: `render`/`render_async`/`components`/`handle` |
| `bot/views/setup_modules/welcome.py` `log.py` | Covered | Fallback 22-line budget |
| `tests/test_zero_hybrid_guard.py` | Modify | 8-file → repo-wide AST hybrid 0 |
| `tests/test_setup_modules_coverage.py` | Create | RED→GREEN 22 lines; asserts handle/render |
| `openspec/changes/v1-postrelease-zero/specs/*` 12 | Modify S1 | 27→0 MODIFIED blocks; `bot-core` untouched |
| `openspec/changes/v1-postrelease-zero/verify-report.md` | Create | Proxy evidence: hashes, validate 35/93, gen9, ty/prek/pytest |

## Interfaces / Contracts

```python
if interaction.guild is not None:
    guild_id = str(interaction.guild.id)  # fixes union-attr

if hasattr(cog.subticket, "callback"):
    await cog.subticket.callback(cog, ctx)  # fixes Group union

# AST guard (repo-wide)
import ast, pathlib

for p in pathlib.Path("bot/cogs").rglob("*.py"):
    assert not any(
        n.attr in ("hybrid_command", "hybrid_group")
        for n in ast.walk(ast.parse(p.read_text()))
        if isinstance(n, ast.Attribute)
    )
```

`SetupModule` protocol (`key`, `permission_key`, `render`, `components`, `handle`) unchanged.

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit S0 ty | 52+8 ignores deleted, 14+4 narrowed | `uv run ty check` 80→0, 10 overrides `warn` stay |
| Unit S0 cov | 22 lines language.py 71-121 | RED `pytest --cov-fail-under=80` 79.78 fail → GREEN ≥80 |
| Unit S1 | hybrid decorators 0, `,` intact | RED AST scan fail → GREEN after swap; `test_comma_timer_invariant` |
| Integration | prek `ty` hook, ruff | `uvx prek run --all-files`, `uv run ruff check bot tests` green |
| Verify | proxy 93/93 + final | `sdd-verify-validate --requirements 35 --scenarios 93`; `uv run pytest --cov-fail-under=80` + `ty` |

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable classification, or process integration. Pure type-hygiene + additive tests + docstring/spec reconciliation; `,` timer is read-only listener.

## Migration / Rollout

Stacked: S0→main, S1→S0. Gate each slice: `uv run ty check` (0), `uv run ruff check bot tests`, `uvx prek run --all-files`, `uv run pytest --cov --cov-fail-under=80`. Rollback: revert merge commit(s); no DDL (29 migrations untouched), no archive/ledger mutation (`sdd-attempt reset --change clean-1.0` forbidden). Proxy blocks `sdd-apply` until `verify-report.md` recorded.

## Open Questions

None. Residual `possibly-unresolved-reference` overrides and `bot/core/i18n.py` hybrid mentions deferred intentionally (outside 27-ref scope).
