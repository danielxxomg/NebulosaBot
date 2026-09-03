# brand-tokens — no-token decision for greeting-templates

**Decision:** No `brand-tokens` delta for `greeting-templates`. The four code-owned templates reuse existing palette tokens from `bot/utils/brand.py` only; no new hex literals or tokens are introduced. This note replaces a delta per the conditional `brand-tokens` capability in `proposal.md` and the `cov-headroom-guard` no-op pattern.

**Why no delta:**

- Existing tokens already cover the required accents/backgrounds:
  - `default` → `brand.ACCENT` (`0xA855F7`) + `brand.CARD_BG_TOP`/`CARD_BG_BOTTOM` + `brand.MUTED_TEXT` + `brand.PANEL_OVERLAY`
  - `gaming_neon` → `brand.ACCENT_A` (`0xFF2E97`) + `brand.ACCENT_B` (`0x00E5FF`) (opt-in neon palette, already present)
  - `sunset_wave` → `brand.WARNING` (`0xF59E0B`) + `brand.ERROR` (`0xEF4444`) for the warm gradient plus `CARD_BG_*`/`MUTED_TEXT`/`PANEL_OVERLAY` for chrome
  - `minimal_light` → `brand.CARD_BG_TOP`/`CARD_BG_BOTTOM` (lightened via existing alpha/overlay math) + `brand.MUTED_TEXT` + `brand.PANEL_OVERLAY` (no new token; procedural lightening only)

All four render branches in `bot/services/greeting_renderer.py` MUST read colors exclusively from `bot/utils/brand.py`; no `#[0-9A-Fa-f]{6}` literal SHALL appear outside `brand.py` (guarded by `tests/test_brand_no_hex.py`). The renderer remains procedural Pillow with `ImageFilter.GaussianBlur` for the neon glow; `sunset_wave` and `minimal_light` reuse the same procedural primitives and the existing token set.

**Verification:** `rg -n "#[0-9A-Fa-f]{6}" bot/` → zero matches outside `brand.py`; `bot/utils/brand.py` exports unchanged (`ACCENT`, `ACCENT_A/B`, `CARD_BG_*`, `MUTED_TEXT`, `PANEL_OVERLAY`, `WARNING`, `ERROR`, etc.) and no `GREETING_ACCENT` reintroduction.

**If new palette hues are ever needed:** open a follow-up `brand-tokens` delta with explicit token definitions and a hex-guard update; this change intentionally adds none.
