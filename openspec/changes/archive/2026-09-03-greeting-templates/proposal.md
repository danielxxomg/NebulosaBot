# Proposal: greeting-templates

## Intent

4 templates (`default`, `gaming_neon`, `sunset_wave`, `minimal_light`) per-kind `welcome_template_id`/`goodbye_template_id`. No assets/fonts/text.

## Scope

### In Scope
- `TEMPLATE_REGISTRY` `greeting_renderer.py` (new via `brand.py`)
- `select_template(config,kind)` new→`themeId`→`default`; `render(alias)` unknown→default
- Migration `030` `IF NOT EXISTS` + `COALESCE` backfill; dual-write
- `StringSelect` `welcome.py`/`goodbye.py` `setup:welcome|goodbye:select_template` + preview
- ~16 `t()` keys; CDC `invalidate_guild` verified

### Out of Scope
- Dashboard (follow-up)
- DB catalogue, uploads, ephemeral preview
- `rank_renderer.py`
- Text/CTA

## Capabilities

### New Capabilities
- None

### Modified Capabilities
- `welcome-goodbye`: registry, per-kind select
- `greeting-config`: per-kind cols, dual-write
- `setup-panel`: per-kind `StringSelect`
- `i18n-system`: `t()` keys
- `brand-tokens`: conditional

## Approach

Stacked ~1,065 vs 1,500.
- **S1 ~385**: `TEMPLATE_REGISTRY` `greeting_renderer.py:75-255`, alias, unknown→default. No DDL.
- **S2 ~270**: `ADD COLUMN IF NOT EXISTS` + `COALESCE WHERE IS NULL`; chain new→legacy→default.
- **S3 ~410**: `welcome.py`/`goodbye.py` 4-opt `StringSelect`, `setup_panel.py`, `to_thread`. Renderer `t()`-free; `greetings.py` untouched.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `greeting_renderer.py` | Modified | registry + alias |
| `greeting_service.py` | Modified | per-kind select |
| `greeting_config.py` | Modified | fields + fallback |
| `greeting_db.py` | Modified | cols |
| `030_greeting_templates.sql` | New | `IF NOT EXISTS` |
| `welcome.py`/`goodbye.py` | Modified | `StringSelect` |
| `locales/{es,en}.json` | Modified | `t()` keys |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Hex outside `brand.py` | Med | tokens only |
| Missing `t()` | Med | both locales |
| Pillow blocks | Low | `to_thread` |
| Cache leak | Low | `cache_key`+`invalidate_guild` |
| Migration | Low | `IF NOT EXISTS` |
| Renderer `t()` | Low | pre-translated |

## Rollback Plan

`themeId` dual-write one cycle. `git revert <sha>`; `DROP COLUMN IF EXISTS "welcomeTemplateId","goodbyeTemplateId"`.

## Dependencies

- Baseline single `themeId`
- `cache.py`+`realtime.py`
- Guards: `test_brand_no_hex`, `test_i18n_key_coverage`, `test_greeting_renderer:96-106`, `test_greeting_service_thread`, `test_migrations`

## Success Criteria

- [ ] 4 PNG (gaming_neon identical, unknown→default)
- [ ] Per-kind fallback + dual-write
- [ ] Both pickers + preview
- [ ] `uv run pytest` + ty/ruff/vulture 0; brand+i18n green; `t()`-free
- [ ] `to_thread` + `cache_key`; `greetings.py` untouched; NULL→default

## Review Workload Forecast

| Slice | Forecast | vs1500 | Chained | Gates |
|-------|----------|--------|---------|-------|
| S1 | ~385 | 26% | base | pytest+ty0/ruff0+hex+t()-free |
| S2 | ~270 | 18% | →S1 | +migrations+cache |
| S3 | ~410 | 27% | →S2 | +i18n+custom_id |
| **Total** | **~1,065** | **71%** | **Yes** | — |

Decision needed before apply: No. Chained PRs recommended: Yes. 400-line risk: Low.

## Gates per Slice

`uv run pytest` + ty/ruff/vulture 0 + `cache_key` + `invalidate_guild` + `IF NOT EXISTS` + brand hex + `t()` + `to_thread` + `t()`-free.
