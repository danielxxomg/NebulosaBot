# Proposal: welcome-svg-foundation (Cycle 1 of 3)

## Intent

Minimal Nebulosa greeting on `python:3.11-slim` (no apt) + hygiene/DRY; Cycle 2 Neon = 1-line swap. Fixes 454L SRP, `#7289da` bypass. Refs `DiagramaSecuencia.mmd`, `Entidad-Relación.mmd`.

## Scope

### In Scope
- `GreetingRenderer`: Pillow default; SVG stub behind `cairosvg` probe+fallback
- Split `image_service.py` → `rank_renderer`+`greeting_renderer`+`shared_assets`; accent→`brand.py`
- Delete `_generate_greeting_card_compatibly` (dead, 0 cov)
- Hygiene: 0.1→0.8, `003`→`003`+`003b`, `.gitignore`+4, `config.yaml` mypy→ty/0.70→0.75/400→800, `AGENTS.md` gaps, `README`, `.env` 3→12, SHA-pin, `updatedAt`
- DRY (-240L): `verifyGuildAdmin`x4→`guards.ts`, `_err`x4→`embeds.py`, `select("*")`x13→`base._guild_select`, `INFO`x2→`brand.INFO`

### Out of Scope
- Cycle 2 Neon; Cycle 3 timer/12h/banana/RLS/voice/moderation; `ScheduledAction`, `has_perm`
- `time.py` vs `timeparse.py` merge (different domains, DO NOT MERGE)
- Delete 58 `archive/*`

## Capabilities

### New Capabilities
- None — internal refactor.

### Modified Capabilities
- `welcome-goodbye`: via `GreetingRenderer`, Nebulosa tokens, native kwargs.
- `greeting-config`: additive `updatedAt`, cache-first + Realtime.
- `brand-tokens`: zero-hex restored.
- `rank-card`: `RankRenderer` extract.

## Approach

Pillow = default. **cairosvg needs `libcairo`**; slim no apt ⇒ SVG behind interface. Inject at `bot/bot.py:215`; Cycle 2 swaps 1 line to `cairosvg`/`resvg-python`. TDD: RED tokens before GREEN.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `image_service.py` | Split | SRP, brand |
| `greeting_service.py` | Modified | shim removal, DI |
| `greetings.py` | Modified | DRY dispatch |
| `embeds.py`, `guards.ts` | Modified/New | DRY extracts |
| `003b_*` | New | rename + `updatedAt` |
| hygiene files | Modified | version/gitignore/config/README/env/workflow |
| `Diagramas/*` | Referenced | sequence/ER/command |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `libcairo` missing | High | Pillow default; probe+log fallback |
| `003` desync | Med | validate live; else reconciliation |
| Shim untested | Low | TDD test first |
| 800-line overrun | Med | auto-chain PR1 hygiene/DRY, PR2 renderer |
| Cache leak | Low | `cache_key(gid, entity)` |

## Rollback Plan

- **Migration**: `git mv 003b_*` revert; live fixup migration.
- **Split**: `git revert` PR2; restart flushes cache.
- Each slice solo-revertible; `uv run pytest --cov=bot` ≥75% after rollback.

## Dependencies

- Pillow 11+ in `uv.lock`; no new dep Cycle 1; `libcairo` audit → Cycle 2.

## Success Criteria

- [ ] Banner via Pillow; 0 hex outside `brand.py`.
- [ ] `GreetingRenderer`; swap 1 line.
- [ ] 0.8.0, `.gitignore`+4, `config.yaml` ty/0.75/800, pinned, `README`+`.env` done.
- [ ] `003` resolved, `updatedAt` additive + Realtime verified.
- [ ] DRY: `guards.ts` x1, `embeds.py` x1, `select("*")` 0, `INFO` 0; -240L.
- [ ] `uv run pytest --cov=bot` ≥75%, `ty`/`ruff` clean; diagrams referenced.
- [ ] ≤800 lines (single PR or 2-slice chain, clean diffs); next = sdd-spec/design.
