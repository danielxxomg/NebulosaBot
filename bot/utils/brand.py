"""Brand color tokens for NebulosaBot.

Purple/violet palette derived from the Nebulosa logo.
All embed colors across the bot MUST import from this module
instead of defining ad-hoc hex constants.
"""

from __future__ import annotations

PRIMARY: int = 0x9B5DE5  # Violet
ACCENT: int = 0xA855F7  # Purple
SUCCESS: int = 0x10B981  # Emerald
WARNING: int = 0xF59E0B  # Amber
ERROR: int = 0xEF4444  # Red
INFO: int = 0x8B5CF6  # Indigo

# Neon theme palette — magenta→cyan diagonal for gaming_neon greeting theme.
ACCENT_A: int = 0xFF2E97  # Magenta
ACCENT_B: int = 0x00E5FF  # Cyan

# Greeting card accent — single source of truth for GreetingRenderer.
# Re-exports ACCENT so the greeting palette is branded, not hardcoded #7289da.
GREETING_ACCENT: int = ACCENT  # alias; value must stay == ACCENT

# ---------------------------------------------------------------------------
# Legacy Discord blurple — one hue, three consumed representations.
# S4 consolidation: legacy surfaces (transcript author color, rank card
# level/bar colors) keep their historical value under these shared names.
# ---------------------------------------------------------------------------
LEGACY_BLURPLE: int = 0x7289DA  # canonical int form
LEGACY_BLURPLE_CSS: str = "#7289da"  # CSS string form
LEGACY_BLURPLE_RGBA: tuple[int, int, int, int] = (114, 137, 218, 255)  # Pillow RGBA form

# ---------------------------------------------------------------------------
# Transcript HTML/CSS palette (S4) — values byte-identical to the original
# inline CSS; only the source of truth moved into brand.py.
# ---------------------------------------------------------------------------
TRANSCRIPT_BG: str = "#36393f"
TRANSCRIPT_HOVER: str = "#32353b"
TRANSCRIPT_AUTHOR: str = LEGACY_BLURPLE_CSS  # alias — same legacy blurple
TRANSCRIPT_MUTED: str = "#72767d"
TRANSCRIPT_BORDER: str = "#42464d"
TRANSCRIPT_TEXT: str = "#dcddde"
TRANSCRIPT_HEADER_TEXT: str = "#fff"

# ---------------------------------------------------------------------------
# Renderer RGBA palette (S4) — byte-identity contract with the golden PNGs:
# values are identical to the pre-consolidation literals in shared_assets /
# rank_renderer / greeting_renderer; only the source of truth moved here.
# ---------------------------------------------------------------------------
CARD_BG_TOP: tuple[int, int, int, int] = (43, 45, 49, 255)
CARD_BG_BOTTOM: tuple[int, int, int, int] = (30, 31, 34, 255)
PLACEHOLDER: tuple[int, int, int, int] = (74, 78, 91, 255)
PLACEHOLDER_INNER: tuple[int, int, int, int] = (56, 59, 68, 255)
PANEL_OVERLAY: tuple[int, int, int, int] = (255, 255, 255, 18)
MUTED_TEXT: tuple[int, int, int, int] = (185, 187, 190, 255)  # == greeting count color
