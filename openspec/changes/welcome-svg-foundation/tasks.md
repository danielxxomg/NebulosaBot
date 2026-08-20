# Tasks: welcome-svg-foundation (Cycle 1 of 3)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~900–1100 (27 files: hygiene + DRY + renderer split) |
| 800-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 hygiene/DRY + updatedAt → PR2 renderer split |
| Delivery strategy | auto-chain |
| Chain strategy | pending (recommend stacked-to-main; confirm before PR open) |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Hygiene + DRY + updatedAt (no renderer) | PR1 | `uv run pytest tests/test_greeting_config.py tests/test_realtime.py -k updatedAt` | `uv run ruff check && uv run ty check && uv run tach check` | revert PR1; hygiene files + DRY extracts + 003b migration independent |
| 2 | Renderer SRP split (shared + Protocol + greeting + rank + wiring) | PR2 | `uv run pytest tests/test_greeting_renderer.py tests/test_rank_renderer.py` | `uv run pytest --cov=bot` (≥75%) | revert PR2; restart flushes cache; `image_service.py` restored |

## Phase 1: Hygiene & Config (PR1)

- [x] 1.1 `pyproject.toml`: version 0.1.0→0.8.0; add CHANGELOG entry
- [x] 1.2 `.gitignore`: add `.ty_cache/`, `.hypothesis/`, `*.tsbuildinfo`, `**/.next/`
- [x] 1.3 `openspec/config.yaml`: mypy→ty, 0.70→0.75, 400→800; refresh stale test count
- [x] 1.4 Create `README.md` (what NebulosaBot is, run steps, architecture brief)
- [x] 1.5 `.env.example`: document all ~12 bot/Discord/feature vars with comments
- [x] 1.6 `.github/workflows/code-quality.yml`: SHA-pin `jscpd`, `vulture`, all external actions
- [x] 1.7 `AGENTS.md`: document cairosvg libcairo constraint, `cache_key` guild-scoping, time.py/timeparse.py do-not-merge
- [x] 1.8 Reconcile duplicate 003 migration: validate live `schema_migrations` or ship no-op reconciliation; ensure ≤1 file with 003 prefix

## Phase 2: DRY Extracts (PR1)

- [x] 2.1 Create `dashboard/lib/guards.ts` shared `verifyGuildAdmin`; 4 action files import + pass error string
- [x] 2.2 Replace `select("*")` x13 in dashboard actions with explicit column lists
- [x] 2.3 Add shared `_err`/`_ok`/`_info` to `bot/utils/embeds.py`; 4 cogs import instead of redefine
- [x] 2.4 Remove local `INFO = from_str("#5865F2")` in `ticket_admin_flow.py` + `ticket_notes_flow.py`; import `brand.INFO`
- [x] 2.5 Add docstrings to `bot/utils/time.py` + `bot/utils/timeparse.py` stating separate domains — **DO NOT MERGE**

## Phase 3: updatedAt Foundation (PR1)

- [x] 3.1 RED: `test_greeting_config` updatedAt round-trip (null preserved, T preserved) via `from_db_row`/`to_db_dict`
- [x] 3.2 GREEN: add `updated_at: datetime | None` to `GreetingConfig`; preserve camelCase `updatedAt` key mapping
- [x] 3.3 `greeting_db.py`: `upsert_greeting_config` sets `updatedAt = now()`; round-trip field
- [x] 3.4 Create `supabase/migrations/003b_updatedAt_greeting_config.sql` — `ALTER TABLE ... ADD COLUMN "updatedAt" timestamptz NULL` (distinct non-003 prefix)
- [x] 3.5 RED: `test_realtime` incremental poll — `updatedAt > $last_check`; null included; `last_check` advances
- [x] 3.6 GREEN: `realtime.py._poll_once`: query `greeting_config` by `updatedAt > $last_check`; null treated as always-changed

## Phase 4: Renderer SRP Split (PR2)

- [ ] 4.1 Create `bot/services/shared_assets.py`: `_card_base`, gradient loop, `_load_font`, `_safe_fetch_avatar`, `_paste_circular_asset` (services layer; no cog/view imports)
- [ ] 4.2 RED: `test_greeting_renderer` — no `#7289da`/`GREETING_ACCENT`; accent from `brand.ACCENT`; font `OSError`→`ImageFont.load_default()` + WARNING
- [ ] 4.3 GREEN: create `bot/services/greeting_renderer.py` — `GreetingRenderer` Protocol + `PillowGreetingRenderer`; reads `brand.ACCENT`, `to_thread`-safe
- [ ] 4.4 RED: `test_rank_renderer` — output byte-identical to pre-split (golden bytes)
- [ ] 4.5 GREEN: create `bot/services/rank_renderer.py` — `RankRenderer` owning `generate_rank_card`; imports `shared_assets`
- [ ] 4.6 RED: `test_bot_probe` — cairosvg ImportError → Pillow + WARNING, no abort; cairosvg present → Pillow still default (Cycle 1)
- [ ] 4.7 GREEN: `bot/bot.py:215` probe `import cairosvg` → inject `PillowGreetingRenderer`; pass to `GreetingService`
- [ ] 4.8 RED: `test_greeting_service` native-kwargs path — exercises `generate_greeting_card` with localized kwargs directly (guard before shim delete)
- [ ] 4.9 GREEN: `greeting_service.py` depend on `GreetingRenderer` interface; delete `_generate_greeting_card_compatibly` shim; `dispatch_greeting` calls renderer via `to_thread`
- [ ] 4.10 `greetings.py`: `/welcome_test` + `/goodbye_test` call renderer via `to_thread`; DRY kwargs assembly
- [ ] 4.11 Remove `generate_rank_card` + `generate_greeting_card` + helpers from `image_service.py`; delete file if no callers remain (verify first)
- [ ] 4.12 `bot/utils/brand.py`: re-export greeting accent token (single source; no palette value change)
- [ ] 4.13 `tach.toml`: confirm `bot.services` declaration covers new modules; no new top-level `[[modules]]` entry

## Phase 5: Verify Gates

- [ ] 5.1 `uv run ruff check` — clean
- [ ] 5.2 `uv run ty check` — clean
- [ ] 5.3 `uv run tach check` — clean; new modules in services layer; no cross-layer violations
- [ ] 5.4 `uv run pytest --cov=bot` — ≥75% coverage
- [ ] 5.5 Verify ≤800 changed lines per PR slice; each slice solo-revertible
