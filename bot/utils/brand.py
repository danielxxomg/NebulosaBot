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

# Greeting card accent — single source of truth for GreetingRenderer.
# Re-exports ACCENT so the greeting palette is branded, not hardcoded #7289da.
GREETING_ACCENT: int = ACCENT  # alias; value must stay == ACCENT
