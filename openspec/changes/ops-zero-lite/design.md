# Design: ops-zero-lite

## Technical Approach

S0 ships net-new (Sentry env-gated, WatchdogCog, rotation.md, backup.yml, Vulture blocking); S1 only `bot/core/cache.py:9-10` header fix. CDC echo, 026 publication, greeting semaphore and transcript `to_thread` are PRESERVED (green). No migration, no product scope, `[]` prefix and `,` timer untouched. TDD `uv run pytest --cov-fail-under=80`.

## Architecture Decisions

### D1 Sentry init

| Option | Tradeoff | Decision |
|---|---|---|
| import side-effect | fail-closed, untestable | Reject |
| `setup_hook()` | couples to Discord | Reject |
| `bot/__main__.py` pre-`asyncio.run` guard | sync, testable | **Choose** |

`dsn=os.getenv("SENTRY_DSN","").strip()`; if set `sentry_sdk.init(dsn, send_default_pii=False, before_send=_scrub)` else no-op. `_scrub` drops token/SUPABASE/DISCORD and raw message. Pin `sentry-sdk==2.22.0` exact.

### D2 WatchdogCog

| Option | Tradeoff | Decision |
|---|---|---|
| reflect loops | brittle | Reject |
| `all_tasks()` | no signal | Reject |
| register+heartbeat timestamps | explicit, `2×interval` | **Choose** |

`bot/cogs/watchdog.py` cog: `@tasks.loop(30)` + `before_loop(wait_until_ready)` + `cog_unload` cancel. `register(name,interval)`/`heartbeat(name)` (monotonic). `now-last>2*interval` → `logger.warning`; `try/except` isolation; zero `discord.*` calls.

### D3 Backup cron

| Option | Tradeoff | Decision |
|---|---|---|
| `supabase db dump` | needs link | Reject |
| `pg_dump` pooler `:5432` via `SUPABASE_DB_URL` | minimal, proven | **Choose** |

`backup.yml` cron `0 2 * * *` + `workflow_dispatch`, SHA-pinned actions, `postgresql-client`, `pg_dump "$SUPABASE_DB_URL" -Fc -f dump.pgdump` (masked), `upload-artifact retention-days:7`, `continue-on-error:false`.

### D4 Vulture blocking

| Option | Tradeoff | Decision |
|---|---|---|
| `pyproject.toml` | no surface | Reject |
| Makefile | bypassable | Reject |
| CI step blocking | single gate, clean #4700 | **Choose** |

Remove `continue-on-error:true` in `code-quality.yml` for `vulture bot/ --min-confidence 80`. Whitelist via `whitelist.py`.

### D5 Rotation docs

| Option | Tradeoff | Decision |
|---|---|---|
| `logrotate` | daemon, panel ignores | Reject |
| `daemon.json` `10m×5` | native ~60 MB | **Choose** |

`docs/ops/rotation.md`: `{"log-driver":"json-file","log-opts":{"max-size":"10m","max-file":"5"}}`, `docker inspect` verify, Pterodactyl unbounded note, rollback `remove keys + reload`.

### D6 Cache header

| Option | Tradeoff | Decision |
|---|---|---|
| rewrite block | noise | Reject |
| one-line fix `Deferred…not wired` → `Realtime-invalidated: guild,greeting_config,ticket,ticket_note,member,economy_config` | minimal | **Choose** |

PRESERVED verify-only; no duplicate tests.

### D7 Slice boundary

| Option | Tradeoff | Decision |
|---|---|---|
| merge S0+S1 | mixes net-new+verify | Reject |
| keep split | focus, S1 one-line rollback | **Choose** |

S0 ~800 lines (53% of 1500); S1 ~40 lines (3%). Protects 0.23pp coverage headroom.

## Data Flow

```
Sentry: DSN? ─yes→ init(_scrub) ─no→ no-op
Watchdog: loops --heartbeat→ {name:last} --30s→ 2×? WARNING (no Discord)
CDC: write --_on_write→ RecentWriteSet(5s) --CDC→ skip if contains else invalidate_guild
Greeting: join --cache-first→ sem(2) locked? drop : to_thread(render)
Backup: cron 02:00 --pg_dump pooler→ dump.pgdump --upload 7d→ FAIL if non-zero
```

## File Changes

| File | Action | Desc |
|---|---|---|
| `bot/cogs/watchdog.py` | Create | WatchdogCog 30s loop, log-only |
| `bot/__main__.py` | Modify | Guarded Sentry + `_scrub` |
| `bot/config.py` | Modify | `SENTRY_DSN` |
| `pyproject.toml` | Modify | `sentry-sdk==2.22.0` |
| `docs/ops/rotation.md` | Create | daemon.json + verify |
| `.github/workflows/backup.yml` | Create | pg_dump 7d SHA-pinned |
| `.github/workflows/code-quality.yml` | Modify | Vulture blocking |
| `bot/core/cache.py:9-10` | Modify | Fix header |

No `030`; 026 shipped.

## Interfaces / Contracts

```python
class WatchdogCog(commands.Cog):
    def register(self, name: str, interval_s: float) -> None: ...
    def heartbeat(self, name: str) -> None: ...
    @tasks.loop(seconds=30)
    async def _check(self) -> None: ...  # 2× → warning
    async def cog_unload(self) -> None: ...  # cancel
if dsn:=os.getenv("SENTRY_DSN","").strip(): sentry_sdk.init(dsn, send_default_pii=False, before_send=_scrub)
```

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit | DSN no-op/present, scrub | `patch.dict` + `patch(sentry_sdk.init)` |
| Unit | stall WARNING, no mutation, 2×, cancel | monotonic + `caplog` + zero mock |
| Unit | no `print`/`stderr`, header | grep + `read_text` |
| Integ | loop → `logging` | raise, assert `Loop._error` |
| Workflow | backup.yml, vulture 0 | YAML + `vulture 80` |

PRESERVED: `test_database.py:1968`+`:2065`, `test_realtime.py`, `test_transcript_service.py:293`, `test_greeting_service_raid.py` (burst + guild-scoped), `test_greeting_service_thread.py:39`, `test_i18n_key_coverage.py`, `tasks/__init__.py:415`. New RED: `test_sentry_noop_without_dsn`, `test_sentry_scrub_no_pii`, `test_watchdog_logs_stall_no_mutation`.

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary. `pg_dump` is static (masked env, no user args); backup workflow has no `git`/`gh pr` routing. No RED tasks required.

## Migration / Rollout

No migration. S0 rollback `SENTRY_DSN=""` + revert cog/dep/workflow; vulture add `continue-on-error`. S1 revert header. Docs rollback `remove keys + reload`. Ship S0 → `uv run pytest --cov-fail-under=80` ≥80.23% + `ty`0 `ruff`0 `vulture`0 → S1.

## Open Questions

- [ ] `SUPABASE_DB_URL` pooler `:5432` secret name.
- [ ] `sentry-sdk` `ty` allowlist if needed.

