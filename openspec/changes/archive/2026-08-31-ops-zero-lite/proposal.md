# Proposal: ops-zero-lite

## Intent

Harden v1.0.0 (c86525a 2973/19 80.23% ty0 ruff0) against unbounded logs, silent loop stalls, unobserved exceptions, blocking transcripts, zero backups, CDC incoherence. No product scope.

## Scope

### In Scope

**S0 obs-zero (~610):** Sentry free-tier (`SENTRY_DSN`); Docker rotation docs (`daemon.json`, Pterodactyl unbounded #4711); watchdog cog + fix `tasks.loop` stderr→`logging` incl `tickets.py:217` (AGENTS.md); `_build_html`→`to_thread`; daily `db dump` cron (pooler 5432); Vulture advisory→blocking (config-only clean #4700).

**S1 CDC+resilience (~480):** wire `_on_write` on member/economy DB (`RecentWriteSet` unused) echo guard (external CDC only); publication migration member/economy_config (follow 026 `IF NOT EXISTS`); greeting Semaphore/debounce (100 joins≠100 renders).

### Out of Scope

`,timer` debounce, Semgrep, mutmut, dashboard QA, multi-template greetings, voice-state, sqlite mirror — parked.

## Capabilities

### New Capabilities

- `ops-observability`: Sentry + watchdog

### Modified Capabilities

- `transcript-service`: `to_thread`
- `cache-sync-realtime`: `_on_write` + publication
- `welcome-goodbye`/`greeting-config`: semaphore/debounce
- `operational-config`: rotation docs
- `qa-ci-pipeline`: dump cron
- `pyproject-toml-qa-config`: Vulture blocking

## Approach

S0: env-gated sentry-sdk, watchdog via `logging` only (AGENTS.md observe+delegate), `to_thread`, backup 7d, Vulture flip. S1: `_on_write`→`RecentWriteSet`+`invalidate` only if CDC≠self; `030` `IF NOT EXISTS`+`guild_id`; Semaphore+debounce. Both TDD (`uv run pytest`, 100% `t()`, `brand.py`).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `bot/cogs/watchdog.py` | New | Watchdog cog |
| `bot/services/transcript_service.py` | Modified | `to_thread` |
| `bot/core/realtime.py`, `bot/services/*` | Modified | `_on_write`, echo guard |
| *(none)* | — | No new DDL — publication already shipped via `migrations/026` [PRESERVED] |
| `.github/workflows/backup.yml`, `pyproject.toml` | Modified | Dump cron, Vulture |
| `docs/ops/*.md` | New | Rotation + DR |
| `bot/locales/{es,en}.json` | Modified | i18n keys |

## Review Workload Forecast

| Slice | Forecast | vs 1500 | Gates |
|-------|----------|---------|-------|
| S0 | ~610 | 41% single PR | 2973/19 --cov-fail-under=80 (0.23pp) ty0 ruff0 prek9 |
| S1 | ~480 | 32% single PR | Same + IF NOT EXISTS, CDC negative test |

Chained PRs: No. Ship sequentially via auto-chain stacked-to-main.

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Coverage <80 (0.23pp) | High | TDD measure --cov per slice |
| CDC echo-storm | Med | RecentWriteSet+source check |
| Sentry noise | Low | Env-gated no PII |
| Watchdog mutates | Low | Observe+log only |

## Rollback Plan

S0: revert cog+dep+workflow; SENTRY_DSN="" disables; Vulture revert; to_thread one-line. S1: revert mixins; DROP PUBLICATION guard; remove semaphore.

## Dependencies

SUPABASE_DB_URL (pooler 5432); SENTRY_DSN optional; no new infra.

## Success Criteria

- [ ] S0: Sentry captures; watchdog logs stall ≤2×; no print/stderr; transcript off loop; dump artifact; Vulture blocking green
- [ ] S1: external CDC invalidates; self-write no echo; migration idempotent; 100 joins bounded
- [ ] Both: pytest ≥2973 cov ≥80.23% ty0 ruff0 i18n 100% `,`+zero-hybrid intact
