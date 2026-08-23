# Tasks: Cycle 4 — Debt Zero

Baseline: `uv run pytest` = 2658 passed / 84.33% cov. Every task keeps it green. TDD red-green for behavior; config tasks exempt but state verification command.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1810 total; S1~420 S2~680 S3~550 S4~160 |
| 800-line (session) budget risk | Low (max slice S2~680, ~120 margin) |
| 400-line (default) budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | S1→S2→S3→S4 stacked-to-main |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | A: 5 gates + apply_escalation + ty fix | S1 | `uv run pytest tests/test_infraction_service.py tests/test_checks.py tests/integration/test_moderation_flow.py` | N/A (mocked services) | `infraction_service.py`, `sentinel.py` decorators/warn-body, `ticket_integrity_flow.py:73` |
| 2 | C-batch: i18n + C5 + C2/C11 + C4/C6–C13 | S2 | `uv run pytest tests/test_i18n_key_coverage.py tests/test_infraction_service.py` | N/A (mocked) | `locales/*.json`, `sentinel.py` C2/C10/C11, `bot.py` C4, `ocio*.py`, `embeds.py`, `realtime.py`, `logging_service.py`, `stellar.py` |
| 3 | F+B toolchain fixes→gates; C14; jscpd ratchet | S3 | `uv run ruff check bot/ tests/ && uv run ty check bot/ tests/ && uv run scripts/jscpd_check.py && uv lock --check` | `scripts/jscpd_check.py`; `uv lock --check` | `pyproject.toml`, `prek.toml`, `scripts/jscpd_check.py`, `reports/jscpd-baseline.json`, `.github/workflows/code-quality.yml`, `tests/test_bot_probe.py` |
| 4 | D AGENTS V3 + E convergence + residual | S4 | `gga --pr-mode --diff-only f77bf38..HEAD` | full suite + prek all-files | `AGENTS.md`, `residual-debt.md` |

## Slice S1 — Sentinel A + escalation + ty fix (~420 ln)

- [x] S1.1 RED `tests/test_infraction_service.py`: apply_escalation MUTE/KICK ok → success fragment; Forbidden → failure fragment, no row/log; unexpected exc propagates (spec: 4 scenarios)
- [x] S1.2 GREEN `bot/services/infraction_service.py`: add `async apply_escalation(*, guild_id, member, moderator, escalation)->str` (D1); `match escalation.action` MUTE→timeout / KICK→kick; insert_infraction; log_moderation_action; catch only `discord.Forbidden`
- [x] S1.3 RED `tests/test_checks.py`: introspect warn/unwarn/mute/unmute/kick = `@can_check("moderation.warn"/.mute/.kick)`; denial raises `CheckFailure` naming permission (spec: 5 "denied" scenarios)
- [x] S1.4 GREEN `bot/cogs/sentinel.py`: swap `@is_mod()`→`@can_check(...)` at warn L285, unwarn L436, mute L514, unmute L597, kick L648 (D2); ban/tempban/unban already gated — untouched
- [x] S1.5 GREEN `bot/cogs/sentinel.py`: slim `warn` body — replace MUTE L332-369 + KICK L370-406 inline blocks with `await svc.apply_escalation(...)`; cog keeps validation + embed only
- [x] S1.6 Update `tests/test_pr2_sentinel_red.py` + `tests/test_s3d1_guardrails.py`: `is_mod`→`can_check(key)` assertions; MissingRole→CheckFailure
- [x] S1.7 Fix ty: `bot/cogs/ticket_integrity_flow.py:73` `invalid-argument-type is_mod_check`
- [x] S1.8 Update `tests/integration/test_moderation_flow.py`: warn→escalation round-trip via service
- [x] S1.9 Verify: `uv run pytest tests/test_infraction_service.py tests/test_checks.py tests/integration/test_moderation_flow.py`; `uv run ty check bot/cogs/ticket_integrity_flow.py` exit 0. Deps: S1.2 before S1.5.

## Slice S2 — C-batch i18n + hygiene (~680 ln)

- [x] S2.1 RED `tests/test_i18n_key_coverage.py` (new): AST-scan `bot/**` for `t(<g>,"literal")`; fail listing missing key + `file:line`; `DYNAMIC_KEY_PATTERNS` allowlist regex tuple (`tickets.timer.unit_*`, `ocio.8ball.r\d+`); unused-key advisory only (spec i18n: 3 scenarios)
- [x] S2.2 GREEN `bot/locales/es.json` + `en.json`: add 9 `tickets.timer.*` keys (scheduled_title/body, unit_second/minute/hour/day) with `{unit}` interpolation (C1); pre-existing keys unchanged
- [x] S2.3 GREEN `bot/locales/es.json` + `en.json`: add `ocio.8ball.embed_title`; `r1`-`r20` byte-unchanged (C1b)
- [x] S2.4 GREEN `bot/cogs/ocio.py`: `/8ball` embed title via `t(guild,"ocio.8ball.embed_title")`; ephemeral, no DB write (spec ocio)
- [x] S2.5 RED `tests/test_infraction_service.py`: expire_tempbans — unban-first; NotFound≡success→deactivate; other fail keeps ACTIVE+warning+skip; next scan re-selects+retries (spec infraction: 6 scenarios)
- [x] S2.6 GREEN `bot/services/infraction_service.py:220-227`: reorder — unban FIRST; NotFound→success→deactivate→count++; other failure→row stays active + `logger.warning` + skip (D3); no retry flag; cadence/log unchanged
- [x] S2.7 GREEN `bot/cogs/sentinel.py` C2: kick final result = permanent channel embed (replicate tempban L1155 two-step) at L694; ban at L798 (specs ephemeral-standard/sentinel-commands/confirm-dialog)
- [x] S2.8 GREEN `bot/cogs/sentinel.py` C11: recompute `expires_at` inside `_do_tempban` after Confirm; single value for DB insert + logs (L1108) (spec tempban "no drift" scenario)
- [x] S2.9 GREEN `bot/cogs/sentinel.py` C10: add `UnbanTarget` dataclass; replace `discord.Object` + monkey-patched `.mention`/`.name` + `type: ignore` at L1236-1240 (spec unban "typed value object" scenario)
- [x] S2.10 GREEN `bot/bot.py` C4: `on_app_command_error` L374 + `on_command_error` L404 — log full exception w/ traceback (`logging.exception`) BEFORE user embed (spec logging: 2 scenarios)
- [x] S2.11 GREEN `bot/cogs/ocio.py` C6: `import io`; replace `__import__("io").BytesIO(data)` at L86
- [x] S2.12 GREEN `bot/services/ocio_service.py` C7: verify intent, remove no-op `if resp == key` at L105
- [x] S2.13 GREEN `bot/utils/embeds.py` C8: delete dead `_err/_ok/_info` aliases L223-232 (already `# noqa: F811`)
- [x] S2.14 GREEN `bot/core/realtime.py` L745-753 + `bot/listeners/voice_listener.py` L140-141 + `bot/bot.py` L216/224/244/256 C9: remove stale mock-era/3d/3f comments
- [x] S2.15 GREEN `bot/cogs/tickets.py:100` C12: demote "checking due tickets" to DEBUG; `bot/services/logging_service.py:270-281`: guard digest `count>0` (spec logging zero-count)
- [x] S2.16 GREEN `bot/cogs/stellar.py:1` C13: align docstring with `locale_str` (locale_str stays ES by design)
- [x] S2.17 Verify: `uv run pytest tests/test_i18n_key_coverage.py tests/test_infraction_service.py`; `uv run ruff check bot/ tests/` zero NEW hits. Deps: S2.1 before S2.2/S2.3; S2.5 before S2.6.

## Slice S3 — F+B toolchain fixes→gates + C14 (~550 ln)

Fixes precede gates (D5/D6). Each gate task's acceptance = its exact gate command zero-hit/exit 0.

- [x] S3.1 F1 GREEN `prek.toml`: remove `uv-check`; add `uv-lock-check` (local id, `entry = "uv lock --check"`, pre-push, priority push); tach hooks unchanged (spec pre-commit "uv lock check"). Verify: `uv lock --check` exit 0
- [x] S3.2 F2 fix BLE001: narrow or reasoned-`# noqa: BLE001` at 38 bot/ + 1 scripts/ sites (per-site, AGENTS.md noqa-justified)
- [x] S3.3 F2 fix ASYNC240: narrow per-file ignores on 5 test files (test_bot_probe:89, test_pr3_ocio_service_red:78, test_remediation_final_partials:149, test_s2d1_context_typing_chars:111, test_schema_inventory_verifier:261)
- [x] S3.4 F2 fix G201/A002/PT011: G201×3 logging-named; A002×5 builtin-shadow; PT011 `match=` at 8 sites
- [x] S3.5 F2 gate `pyproject.toml`: `required-version = "0.15.20"`; `explicit-preview-rules = true`; re-select wanted preview rules after diff; drop stale per-file-ignores; add `ANN,PYI,PGH003`; PLC0415 comment-advisory (NEVER select); `select` += `ASYNC,BLE,G,A,PT011`. Verify: `uv run ruff check bot/ tests/` zero-hit
- [x] S3.6 F3 narrow `bot/cogs/**` + `tests/**` ty overrides → per-file entries per scope (D6)
- [x] S3.7 F3 gate `pyproject.toml`: add `[tool.ty.terminal] error-on-warning = true` LAST. Verify: `uv run ty check bot/ tests/` exit 0 — gate staged but deferred (see S3 deviations — tests 495 warns)
- [x] S3.8 B RED `tests/test_jscpd_check.py` (new, threat-matrix): argv assertion (`npx jscpd@4.0.1`, no `shell=True`); bad JSON → exit 1; over-ceiling → exit 2; within → exit 0 (fake `subprocess.run`) (design Threat Matrix)
- [x] S3.9 B GREEN `scripts/jscpd_check.py` (new): run pinned `jscpd@4.0.1` over `bot/`+`tests/`, JSON reporter, tmpdir, parse `statistics.clone.percentage`, exit 0/2/1 per spec; reads `reports/jscpd-baseline.json` `{"bot":f,"tests":f}`
- [x] S3.10 B GREEN `prek.toml`: add `jscpd-check` local hook pre-push, `files = "^(bot/|tests/)"`, priority push. Verify: `uv run scripts/jscpd_check.py` exit 0
- [x] S3.11 B calibrate `reports/jscpd-baseline.json` (new): ceiling = measured + 0.5pp per scope; JSON-only commit (spec calibration)
- [x] S3.12 B GREEN `.github/workflows/code-quality.yml`: drop `continue-on-error`; run `scripts/jscpd_check.py` same pin (spec CI). Verify: checker exit 0
- [x] S3.13 C14 GREEN `tests/test_bot_probe.py`: patch DB/cache, call real `NebulosaBot.setup_hook` (remove inline re-impl L60-72). Verify: `uv run pytest tests/test_bot_probe.py`
- [x] S3.14 Verify: `uv run ruff check bot/ tests/` zero; `uv run ty check bot/ tests/` exit 0; `uv run scripts/jscpd_check.py` exit 0; `uv lock --check` exit 0. Deps: S3.2-S3.4 before S3.5; S3.6 before S3.7; S3.9 before S3.10-S3.12.

## Slice S4 — D AGENTS V3 + E convergence (~160 ln)

- [x] S4.1 GREEN `AGENTS.md`: title→V3; Architecture += `cache_key(guild_id, entity)` mandate; Database += `IF NOT EXISTS` DDL; Discord.py += `t()` mandatory + `can_check` strict; Anti-patterns += matching ❌ rows (D9, spec docs-manual). V3 lands only when tree conforms.
- [x] S4.2 Verify GGA byte-identical: `git diff f77bf38..HEAD -- AGENTS.md` shows GGA "Review Discipline" section unchanged (byte-identical preservation check)
- [x] S4.3 E convergence round 1: `gga --pr-mode --diff-only f77bf38..HEAD` + `uv run pytest` + `prek run --all-files`; fix ≤2 rounds
- [x] S4.4 E survivors → `openspec/changes/cycle-4-debt-zero/residual-debt.md` (D10)
- [x] S4.5 Verify: suite green ≥84.33% cov; `prek run --all-files` clean. Deps: S4.1 after S1-S3 tree conforms.

## Cross-slice regression (final)

- [x] X.1 `uv run pytest` full suite green (≥2658 passed, ≥84.33% cov); `prek run --all-files` clean; `gga --pr-mode --diff-only f77bf38..HEAD` clean. Covers all 13 delta specs.
