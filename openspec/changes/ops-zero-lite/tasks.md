# Tasks: ops-zero-lite

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | S0 ~800 (53% of 1500), S1 ~40 (3%), total ~840 |
| 400-line budget risk | High (S0>400), Low vs 1500 |
| Chained PRs recommended | No (1500 budget allows single-PR slices) |
| Suggested split | PR1 S0 obs-zero → PR2 S1 header (stacked-to-main) |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| S0 | Sentry+Watchdog+backup+rotation+Vulture | PR1 → main | `uv run pytest -k "sentry or watchdog" --cov-fail-under=80` | `SENTRY_DSN="" python -m bot` no-op; DSN set init; `vulture bot/ --min-confidence 80` | Revert `bot/__main__.py`, `bot/cogs/watchdog.py`, `pyproject.toml`, `backup.yml`, `code-quality.yml:41`, `docs/ops/rotation.md` |
| S1 | cache header + guards | PR2 → main (stacked) | `uv run pytest tests/test_greeting_service_raid.py --cov-fail-under=80` | N/A docs-only | Revert `bot/core/cache.py:9-10` |

## Phase S0: obs-zero (NET-NEW, RED→GREEN)

- [ ] S0.1 Secrets: `grep -rn SUPABASE .github/workflows/*.yml`=0 hits → use `SUPABASE_DB_URL` (matches `live_catalog.py:101` fallback); pin `sentry-sdk==2.22.0` in `pyproject.toml`
- [ ] S0.2 RED Sentry: `tests/test_ops_observability.py::TestSentryGate` failing for `ops-observability` DSN present/absent+No PII (patch `sentry_sdk.init`, assert `_scrub` drops token/SUPABASE/DISCORD)
- [ ] S0.3 GREEN Sentry: `bot/__main__.py` add pre-`asyncio.run` guard `sentry_sdk.init(dsn, send_default_pii=False, before_send=_scrub)` else no-op; implement `_scrub` per D1
- [ ] S0.4 Dep+ty: `uv sync --locked`+`uv run ty check` must stay 0; if breaks add narrow `tool.ty.overrides` for `bot/__main__.py` only
- [ ] S0.5 RED Watchdog: failing `TestWatchdogCog` for `ops-observability` stall WARNING 2× interval (`monotonic`+`caplog`) + no mutation (zero `discord.*`)+`cog_unload` cancel
- [ ] S0.6 GREEN Watchdog: create `bot/cogs/watchdog.py` `WatchdogCog` `register`/`heartbeat` monotonic, `@tasks.loop(30)`+`before_loop`+`cog_unload`, `2×→logger.warning`, isolated, zero Discord; add to `bot/bot.py:EXTENSIONS` per D2
- [ ] S0.7 Backup: create `.github/workflows/backup.yml` `cron "0 2 * * *"`+`workflow_dispatch`, SHA-pinned, `pg_dump "$SUPABASE_DB_URL" -Fc`, `upload-artifact retention-days:7`, `continue-on-error:false`, doc secret in `docs/ops/rotation.md`
- [ ] S0.8 Rotation: create `docs/ops/rotation.md` `daemon.json {"max-size":"10m","max-file":"5"}` ~60 MB, `docker inspect` verify, Pterodactyl unbounded #4711, rollback `remove keys+reload`
- [ ] S0.9 Vulture: edit `.github/workflows/code-quality.yml:41` remove `continue-on-error: true` for `vulture bot/ --min-confidence 80` (#4700 clean)
- [ ] S0.10 PRESERVED verify: `uv run pytest tests/test_database.py::TestMemberEconomyOnWriteHooks tests/test_transcript_service.py -k to_thread tests/test_greeting_service_raid.py -q --cov-fail-under=80` green (no dup tests)
- [ ] S0.11 S0 gates: `uv run pytest --cov-fail-under=80` ≥2973 cov≥80, `ty 0 ruff 0 vulture 0 prek 9`, `bot/bot.py:_noop_prefix==[]` and `","` in `tickets.py:241` intact

## Phase S1: header fix + PRESERVED

- [ ] S1.1 Fix `bot/core/cache.py:9-10` remove `Deferred: member, economy_config — not wired; TTL-only` keep `Realtime-invalidated: ...,member,economy_config` per `cache-sync-realtime` [NET-NEW]
- [ ] S1.2 PRESERVED CDC: `uv run pytest tests/test_database.py::TestMemberEconomyOnWriteHooks tests/test_realtime.py -k cdc --cov-fail-under=80` green (`SUBSCRIBED_TABLES`, `RecentWriteSet` 5s) [`test_database.py:1968,2065`]
- [ ] S1.3 PRESERVED greet: `uv run pytest tests/test_greeting_service_raid.py tests/test_greeting_service_thread.py tests/test_transcript_service.py --cov-fail-under=80` green (sem2 drop, `to_thread`, `t()`, `cache_key`) [`raid`, `transcript:293`]
- [ ] S1.4 Final gates+ledger: `uv run pytest --cov=bot --cov-fail-under=80` ≥2973 cov≥80.23%, `ty 0 ruff 0 vulture 0`, record SHA+`daemon.json 10m×5`+SHA pins+`send_default_pii=False`

## Notes

- Threat Matrix N/A per design; no 030 (026 shipped); NET-NEW cites spec scenario, PRESERVED cites existing test (D6).
