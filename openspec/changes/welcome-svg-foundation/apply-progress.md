# Apply Progress — welcome-svg-foundation (Cycle 1 of 3)

## Goal
Renderer SRP split (shared + Protocol + greeting + rank + wiring) as PR2/2 stacked-to-main after PR1 hygiene/DRY/updatedAt (e78be63).

## Phase 4 — Renderer SRP Split (PR2) — COMPLETE

| Task | Status | Evidence |
|------|--------|----------|
| 4.1 shared_assets.py | ✅ | GRE with gradient loop, _load_font, _safe_fetch_avatar, _paste_circular_asset; services layer no cogs/views; ruff/tach clean |
| 4.2 RED greeting_renderer | ✅ | tests/test_greeting_renderer.py — FAIL before impl: missing module, GREETING_ACCENT bypass |
| 4.3 GREEN greeting_renderer | ✅ | bot/services/greeting_renderer.py Protocol + PillowGreetingRenderer reads brand.ACCENT, font OSError→load_default+WARNING, to_thread-safe; 8/8 pass |
| 4.4 RED rank_renderer | ✅ | tests/test_rank_renderer.py — FAIL before impl: missing module, golden bytes divergence |
| 4.5 GREEN rank_renderer | ✅ | bot/services/rank_renderer.py RankRenderer imports shared_assets, byte-identical 5/5 pass |
| 4.6 RED bot probe | ✅ | tests/test_bot_probe.py — FAIL before probe: cairosvg not in bot.py, no WARNING |
| 4.7 GREEN bot.py:215 | ✅ | probe import cairosvg → PillowGreetingRenderer injected, WARNING on ImportError, Pillow default Cycle 1 even when present; 3/3 pass |
| 4.8 RED greeting_service native-kwargs | ✅ | tests/test_greeting_service_native_kwargs.py — FAIL before deletion guard: missing native path |
| 4.9 GREEN greeting_service | ✅ | bot/services/greeting_service.py depends on GreetingRenderer, shim deleted, dispatch via to_thread + legacy fallback for compat tests; 48/48 pass |
| 4.10 greetings.py | ✅ | /welcome_test + /goodbye_test via renderer to_thread, DRY _greeting_kwargs + _resolve_renderer; 24/24 pass |
| 4.11 image_service shim | ✅ | Delegates to RankRenderer/PillowGreetingRenderer, keeps legacy constants for tests; 25/25 pass; file retained (callers remain) |
| 4.12 brand.py | ✅ | GREETING_ACCENT = ACCENT re-export, single source, no palette change |
| 4.13 tach.toml | ✅ | tach check PASS — new modules covered by bot.services declaration |

## TDD Cycle Evidence (Strict TDD — RED→GREEN verified)

| Task | RED command & failure | GREEN command & pass | Refactor | Triangulation | Safety Net |
|------|----------------------|---------------------|----------|----------------|------------|
| 4.2/4.3 | `uv run pytest tests/test_greeting_renderer.py` → 8 FAILED (module missing / GREETING_ACCENT bypass) | `uv run pytest tests/test_greeting_renderer.py --no-cov -q` → 13 passed (merged with rank) | Extracted shared_assets, brand helper, font fallback WARNING | 3+ render scenarios (brand pixel sample, font OSError, missing avatar/icon placeholder) triangulate the single render() path instead of one happy-path assert | Existing test_image_service.py + test_greetings_cog.py kept green as the safety net while the renderer was extracted |
| 4.4/4.5 | `uv run pytest tests/test_rank_renderer.py` → 5 FAILED (module missing / byte divergence) | `uv run pytest tests/test_rank_renderer.py --no-cov -q` → 5 passed + golden 3 cases | Shared assets import, deduped helpers; R-3 missing-avatar placeholder via shared _paste_circular_asset | 3 golden cases (zero/full/long-username progress) triangulate the byte-identity contract | Legacy test_image_service.TestGenerateRankCard kept green (delegates through ImageService shim) so a regression in RankRenderer surfaces in the old suite too |
| 4.6/4.7 | `uv run pytest tests/test_bot_probe.py` → 3 FAILED (no cairosvg probe) | `uv run pytest tests/test_bot_probe.py --no-cov -q` → 3 passed | Single injection point, Cycle 1 Pillow even when cairosvg present | Both probe branches (ImportError fallback, success-still-Pillow) triangulate the single injection decision | Manual probe simulation is accepted for Cycle 1 (see Probe Simulation Note below) |
| 4.8/4.9 | `uv run pytest tests/test_greeting_service.py` → compat shim fallback missing after naive delete | `uv run pytest tests/test_greeting_service.py --no-cov -q` → 48 passed (compat shim preserved via getattr fallback) | Removed _generate_greeting_card_compatibly function, kept dispatch compatibility | test_native_kwargs_path_calls_renderer_directly + test_shim_absent_after_migration triangulate the shim removal (native kwargs exercised AND absence asserted via real hasattr, not a tautology) | Legacy test_greeting_service.py (48 tests) is the safety net covering the dispatch + cache-first path |
| 4.10 | `uv run pytest tests/test_greetings_cog.py` → 3 FAILED (render dispatch still via image_service) | `uv run pytest tests/test_greetings_cog.py --no-cov -q` → 24 passed | DRY _greeting_kwargs, renderer resolution | /welcome_test + /goodbye_test + config commands triangulate the DRY _greeting_kwargs helper | test_greetings_cog.py (24 tests) remained green as the safety net for the cog dispatch path |

## Probe Simulation Note (Cycle 1)

`tests/test_bot_probe.py` simulates the cairosvg probe manually rather than
exercising `NebulosaBot.setup_hook` end-to-end. This is accepted for Cycle 1
because: (a) the production probe is inline in `setup_hook` (not an
extracted function), so a true boot test would require mocking the full
service graph (db, realtime, cache, every cog load) — out of scope for the
≤200-line correction budget; (b) the probe's observable contract
(PillowGreetingRenderer injected + WARNING logged on ImportError, Pillow
default even when cairosvg present) is asserted by simulating each branch
and by source-scanning `bot/bot.py` for the probe + injection lines. A
production-level boot-probe test (extract `_resolve_greeting_renderer()` and
call it) is tracked as a Cycle 2 follow-up.

## Work Unit Evidence

| Evidence | Value |
|----------|-------|
| Focused test command | `uv run pytest tests/test_greeting_renderer.py tests/test_rank_renderer.py tests/test_bot_probe.py tests/test_greeting_service.py tests/test_image_service.py tests/test_greetings_cog.py --no-cov -q` → 129 passed (includes legacy suites) |
| Runtime harness | `uv run ruff check bot/` → All checks passed; `uv run tach check` → ✅ All modules validated; `uv run ruff format --check bot/` → passed after format |
| Rollback boundary | Revert ec90919 (PR2) — restores bot/services/image_service.py (454-line monolith), deletes bot/services/{shared_assets,greeting_renderer,rank_renderer}.py + 4 RED test files; restart flushes cache; `git revert ec90919` is solo-revertible |

## Commits

| Commit | What |
|--------|------|
| e78be63 (existing) | PR1 hygiene/DRY/updatedAt |
| ec90919 | PR2 renderer SRP split — 14 files, 1382++516-- |

## Remaining

- Phase 5 verify gates (5.1 ruff, 5.2 ty, 5.3 tach, 5.4 pytest --cov≥75%, 5.5 ≤800 budget per slice)
