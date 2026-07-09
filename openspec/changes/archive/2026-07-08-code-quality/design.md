# Design: Code Quality Consolidation

## Technical Approach

Implement a small refactor/infrastructure slice with no behavior change: extract the fallback prefix to a zero-dependency constants module, remove the duplicate avatar helper from the cog, and add report-only duplication/dead-code CI. Specs are intentionally absent; verification follows `specs/README.md` success criteria.

## Architecture Decisions

| Decision | Choice | Alternatives considered | Rationale |
|---|---|---|---|
| Prefix source | Create `bot/constants.py` with `FALLBACK_PREFIX = "nb!"` | Import `_FALLBACK_PREFIX` from `bot.bot` | `bot.bot` imports services/cogs and is a bad shared dependency. A constants module has no imports, avoiding cycles. |
| Avatar helper | Keep one helper in `bot/services/greeting_service.py`; import it in `bot/cogs/greetings.py` | Move to new utility module or keep duplicate | New utility module is extra churn for one helper. Keeping the service helper preserves existing dispatch behavior and removes cog duplication. |
| CI quality checks | Add `.github/workflows/code-quality.yml` with jscpd + vulture steps using `continue-on-error: true` | Add Makefile-only targets or fail CI | Workflow visibility is better than local-only targets; report-only avoids blocking while thresholds/whitelists are tuned. |
| Git cleanup | Put branch/stash cleanup in `tasks.md` runbook only | Script cleanup in repo | Branch and stash deletion are one-time operator actions, not maintainable code. |

## Data Flow

    Prefix consumers ──→ bot.constants.FALLBACK_PREFIX
         │
         ├─ bot.bot prefix callable
         ├─ GuildConfig defaults/from_row
         ├─ GuildDBMixin ensure_guild_exists
         ├─ GuildService defaults
         └─ CoreCog help fallback

    GreetingsCog test commands ──→ greeting_service._resolve_avatar_url()
    GitHub Actions ──→ jscpd/vulture reports ──→ non-blocking CI annotations/logs

## File Changes

| File | Action | Description |
|---|---|---|
| `bot/constants.py` | Create | Define `FALLBACK_PREFIX` as the single production literal source. |
| `bot/bot.py` | Modify | Import `FALLBACK_PREFIX`; remove local `_FALLBACK_PREFIX`. |
| `bot/models/guild.py` | Modify | Use `FALLBACK_PREFIX` for dataclass default and DB-row fallback. |
| `bot/core/db/guild_db.py` | Modify | Use `FALLBACK_PREFIX` in default upsert payload. |
| `bot/services/guild_service.py` | Modify | Use `FALLBACK_PREFIX` for missing-row and join defaults. |
| `bot/cogs/core.py` | Modify | Use `FALLBACK_PREFIX` for help-prefix fallback. |
| `bot/cogs/greetings.py` | Modify | Delete local `_resolve_avatar_url`; import existing helper from greeting service. |
| `.github/workflows/code-quality.yml` | Create | Report-only jscpd and vulture workflow, separate from the blocking QA matrix. |
| `tests/test_code_quality_config.py` | Create | Structural tests for single production prefix literal, single avatar helper definition, and report-only workflow. |

## Interfaces / Contracts

```python
# bot/constants.py
FALLBACK_PREFIX = "nb!"
```

No public runtime API changes. The greeting avatar helper remains internal and returns `str | None`.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | Constant value and consumers still return default prefix | Add/import `FALLBACK_PREFIX` in targeted tests where defaults are asserted. Existing tests may keep literal `"nb!"` when checking user-visible help output. |
| Structural | Production duplication removed | `tests/test_code_quality_config.py` scans `bot/**/*.py`: `"nb!"` only in `bot/constants.py`; `_resolve_avatar_url` definition only in `bot/services/greeting_service.py`. |
| CI config | jscpd/vulture are report-only | Parse `.github/workflows/code-quality.yml` and assert commands exist with `continue-on-error: true`. |
| Regression | Full bot behavior | Run `uv run pytest --cov-fail-under=75`, plus existing ruff/mypy/bandit gates. |

## Migration / Rollout

No migration required. CI checks are non-blocking. Git branch/stash cleanup will be an explicit runbook task in `tasks.md`, not implementation code.

## Open Questions

None.
