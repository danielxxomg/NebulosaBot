# Design: Tooling Rigor Upgrade

## Technical Approach

Upgrade QA configuration in place, then clear surfaced debt before making the gates blocking. The proposal/specs map to four existing control files (`pyproject.toml`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`, `Makefile`) plus code/test fixes required by the new ruff and mypy gates. Preflight found the raw new ruff selection reports **1421 errors** across `bot/ tests/` (**8 safe fixable**, **78 unsafe fixable**) before the planned `tests/` ignores are applied; `mypy --strict bot/core/realtime.py` reports **8 errors** as a representative strict-mode sample.

## Architecture Decisions

| Area | Option / tradeoff | Decision |
|------|-------------------|----------|
| Ruff strategy | Enable all 14 groups now vs. staged groups. Staging lowers short-term churn but weakens the spec. | Add the full select list plus `max-complexity = 15`; run auto-fix first, then manually fix remaining violations. |
| Mypy strategy | Keep project-wide `attr-defined` suppression vs. strict mode with targeted overrides. | Set `strict = true`; remove global `disable_error_code`; keep only `[[tool.mypy.overrides]]` for known modules such as `bot.bot`. |
| Pre-commit strategy | Keep ratcheted file allowlists vs. full `bot/ tests/` scope. | Use `files: ^(bot/|tests/)` for ruff and mypy hooks so new code cannot bypass gates. |
| CI changes | Keep current 3-version matrix vs. production-aligned matrix. | Add Python 3.13 while retaining fail-fast disabled. |
| Coverage gate | Let each tool define its own threshold vs. one 75% ratchet everywhere. | Enforce 75 in pyproject, CI pytest invocation, and Makefile `test`/`cov`. |
| Debt clearing | Blanket `noqa`/overrides vs. fix-forward. | Prefer real fixes; use `noqa` or mypy overrides only when justified and narrow. |

## Data Flow

```text
Config tests fail first -> edit QA config -> ruff --fix
        -> manual ruff fixes -> strict mypy fixes/overrides
        -> pre-commit --all-files -> uv run pytest -> CI matrix
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `pyproject.toml` | Modify | Ruff select list, mccabe limit, `tests/` ignores, mypy strict, 75% pytest gate. |
| `.pre-commit-config.yaml` | Modify | Replace hook allowlists with `^(bot/|tests/)`; keep ruff before mypy. |
| `.github/workflows/ci.yml` | Modify | Add `3.13`; raise workflow coverage gate to 75. |
| `Makefile` | Modify | Align `test` and `cov` with `--cov-fail-under=75`. |
| `bot/**/*.py`, `tests/**/*.py` | Modify as needed | Clear violations surfaced by new ruff/mypy gates; examples include `tests/test_xp_listener.py` asserts until test ignores land. |

## Interfaces / Contracts

```toml
[tool.ruff.lint]
select = ["E", "W", "F", "I", "N", "UP", "B", "SIM", "RUF", "S", "C4", "C90", "RET", "T20", "ARG", "DTZ", "EM", "T10", "TRY", "RSE", "FLY", "PERF", "FURB"]

[tool.ruff.mccabe]
max-complexity = 15

[tool.ruff.lint.per-file-ignores]
"tests/**/*.py" = ["S101", "ARG", "T20"]

[tool.mypy]
strict = true

[[tool.mypy.overrides]]
module = "bot.bot"
disable_error_code = ["attr-defined"]
```

```yaml
files: ^(bot/|tests/)
python-version: ["3.11", "3.12", "3.13", "3.14"]
run: uv run --extra dev pytest --cov-fail-under=75
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit/config | Ruff config includes 14 groups, mccabe 15, test ignores. | Add TOML/YAML validation tests before config edits. |
| Unit/config | Mypy strict enabled and `attr-defined` only per-file. | Validate `tool.mypy` and overrides. |
| Integration/config | Pre-commit scopes ruff/mypy to all `bot/ tests/`. | Validate hook order and `files` pattern. |
| Integration/CI | Matrix includes 3.13 and coverage gate is 75. | Validate workflow YAML and Makefile commands. |
| Final gate | Tooling passes. | `uv run ruff check bot/ tests/`, `uv run mypy --strict bot/ tests/`, `pre-commit run --all-files`, `uv run pytest`. |

## Migration / Rollout

No data migration required. Roll out in one implementation slice, but execute internally as: tests first, config edits, automated ruff fixes, manual debt clearing, final verification. Do not merge while the 1421 raw ruff violations or strict mypy errors remain; narrow suppressions must include rationale.

## Open Questions

- [ ] Should CI lint/type commands switch from explicit file lists to `bot/ tests/` in the same slice as pre-commit, or remain separately ratcheted until the debt pass proves clean?
