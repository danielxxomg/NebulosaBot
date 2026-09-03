# Tasks: greeting-templates

## Review Workload Forecast

| Slice | Goal | Est | %1500 | Base |
|-------|------|-----|-------|------|
| S1 | Registry+policy no DDL | ~385 | 26% | master |
| S2 | Migration 030+dual-write | ~270 | 18% | S1 |
| S3 | Pickers+16 keys | ~410 | 27% | S2 |
| Total | Stacked | ~1,065 | 71% | — |

Estimated changed lines: ~1,065 vs 1,500
400-line budget risk: Low
Chained PRs recommended: Yes
Chain strategy: stacked-to-master
Delivery strategy: auto-chain
Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-master
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | PR | Focused test | Runtime harness | Rollback |
|------|------|----|--------------|-----------------|----------|
| S1 | Registry | PR1→master | `uv run pytest tests/test_greeting_template_registry.py -q --randomly-seed=42` | `rg "t\(|#[0-9A-Fa-f]{6}" greeting_renderer.py`=0; gaming_neon bytes equal | Revert renderer/service |
| S2 | Migration | PR2→S1 | `uv run pytest tests/test_migrations.py -q --randomly-seed=42` | Apply 030 twice; COALESCE `gaming_neon`/null | Revert 030, config/db |
| S3 | Pickers+i18n | PR3→S2 | `uv run pytest tests/test_i18n_key_coverage.py -q --no-cov` | `/setup` 4 opts via `t()`+preview PNG | Revert welcome/goodbye, locales |

## Slice S1 — Registry (~385)

TDD: NEW `tests/test_greeting_template_registry.py` first. Gates: `uv run pytest -q --randomly-seed=42 --cov=bot --cov-fail-under=80` green, `ty`/`ruff`/`format`/`vulture`/`tach` 0, `test_brand_no_hex` pass, renderer `t()`-free, `gaming_neon` byte-identity `GaussianBlur(8)`.

- [x] S1.1 RED `tests/test_greeting_template_registry.py` 4 keys, unknown→default, t()-free, no hex, byte-identity + extend `test_greeting_service.py` — ~90 ln — AC: fails pre-impl
- [x] S1.2 `bot/services/greeting_renderer.py` Template+registry 4, `_render_sunset/minimal` brand-only, dual-param `render(template_id,theme_id)` keep 75-99 — ~140 ln — AC: hex 0 outside brand
- [x] S1.3 `bot/services/greeting_service.py` `select_template` new→themeId→default + `asyncio.to_thread(render,…)` — ~60 ln — AC: `test_greeting_service_thread` pass

## Slice S2 — Persistence (~270)

TDD: extend `test_greeting_config`+`test_migrations` first. Gates: S1+idempotency+`cache_key`/`invalidate_guild`+COALESCE.

- [x] S2.1 RED extend `tests/test_greeting_config.py` fallback+welcome-wins + `tests/test_migrations.py` — ~60 ln — AC: fails pre-migration
- [x] S2.2 `supabase/migrations/030_greeting_templates.sql` `ADD COLUMN IF NOT EXISTS`+`COALESCE WHERE IS NULL` — ~15 ln — AC: twice 0 error; `gaming_neon` backfilled, null stays null
- [x] S2.3 `bot/models/greeting_config.py` 2 fields+`from_db_row`+`to_db_dict` welcome-wins + `bot/core/db/greeting_db.py` — ~80 ln — AC: `test_greeting_config` cov≥80 green

## Slice S3 — Pickers+i18n (~410)

TDD: extend i18n/setup tests first. Gates: prior+16 keys both locales+`custom_id` `setup:welcome|goodbye:select_template`+`greeting.manage`+`greetings.py` untouched.

- [x] S3.1 RED extend tests 4 opts+16 keys — ~70 ln — AC: `test_i18n_key_coverage` fails missing keys
- [x] S3.2 `bot/locales/es,en.json` 16 keys — ~40 ln — AC: coverage green both locales
- [x] S3.3 `bot/views/setup_modules/welcome.py`+`goodbye.py` StringSelect via `t()`, `set_*`→`save_config`→`cache.invalidate`, `render_async`+`_handle_test` via `to_thread` — ~180 ln — AC: `uv run pytest -k setup_module -q --no-cov` green

## Work-Unit Commits

Chained PRs: after each slice's gates pass orchestrator merges stacked-to-master; apply does NOT push/open PRs. Stage ONLY `bot/services|models|core/db|views`, `supabase/migrations`, `locales`, `tests`; NEVER `AGENTS.md`, `openspec/`, `dashboard/`. One per slice.

- [x] C1 `feat(ops): greeting template registry with per-kind selection policy` — renderer/service/test — Ledger `files/lines/collected/cov before→after seed42`
- [x] C2 `feat(db): per-kind greeting template columns with themeId dual-write` — 030/config/db/tests — Ledger files 173→173, lines 61,214→61,574, collected 3007→3034, cov seed42 81.65%→81.65% (commit 0bf701e)
- [x] C3 `feat(setup): template pickers for welcome and goodbye panels` — welcome/goodbye/locales/tests — Ledger files 173→173, lines 61,574→62,103, collected 3034→3049, cov seed42 81.65%→81.71% (commit 7b7d27c)

## Migration Note

`030` `IF NOT EXISTS`+`COALESCE`; `test_migrations.py` passes twice. Verify `gaming_neon`→cols filled; null→null→`default`.

## S1 CI Fix Note (post-apply, pre-merge)

- CI qa-matrix caught `TestGamingNeonByteIdentity::test_gaming_neon_via_template_id_matches_baseline` failing: frozen cross-env sha256 is not portable (PNG bytes vary across environments despite same Pillow 12.3.0 — encoder/zlib differences). One-time pre/post byte-identity remains proven at apply time in a single env (sha256 c59de301…).
- Fix: replaced frozen-hash regression test with portable assertions — in-run `template_id` vs `theme_id` byte consistency (existing test), neon ≠ default bytes, and ACCENT_A/B pixel-scan via `img.load()` (house pattern `test_greeting_neon_renderer.py:148-173`; `getdata()` is deprecated in Pillow 12.3 and pyproject `filterwarnings=["error"]` raises it).
- `uvx prek run --all-files` transient failure (timeout=60s cold hook-env hydration) passed on re-run; no code change.
