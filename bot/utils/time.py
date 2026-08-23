"""Duration parser — converts human-readable strings to seconds.

Used by SentinelCog to parse moderation timeout durations such as
"1h", "30m", "2d", or compound like "1h30m".

Returns 3600 (1 hour) for any unparseable input so mute commands
degrade gracefully when the user provides a malformed duration.

NOTE: This module is distinct from :mod:`bot.utils.timeparse` (DB
timestamp → datetime parsing). They serve different domains and MUST
NOT be merged — DO NOT MERGE with ``timeparse.py``. See
``bot/utils/timeparse.py`` for the separate domain.
"""

from __future__ import annotations

import re

from bot.core.i18n import t

# Map single-letter suffix to seconds.
_UNIT_TO_SECONDS: dict[str, int] = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
}

# Extended map for strict parser (adds weeks/years).
_STRICT_UNIT_TO_SECONDS: dict[str, int] = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
    "y": 31536000,
}

# Matches one or more (number)(unit) pairs, e.g. "1h30m", "2d", "30s".
_DURATION_RE = re.compile(r"(\d+)([smhd])")

# Strict: leading comma, then one or more (number)(unit) with optional spaces.
_STRICT_RE = re.compile(r"^,\s*(\d+\s*[smhdwy]\s*)+$", re.IGNORECASE)
_STRICT_FIND_RE = re.compile(r"(\d+)\s*([smhdwy])", re.IGNORECASE)

# Default fallback when the input cannot be parsed.
_DEFAULT_SECONDS = 3600  # 1 hour


def parse_duration(text: str) -> int:
    """Convert a human-readable duration string into total seconds.

    Supported suffixes: ``s`` (seconds), ``m`` (minutes), ``h`` (hours),
    ``d`` (days).  Compound strings like ``"1h30m"`` are supported by
    summing each ``(number)(unit)`` pair.

    Args:
        text: A duration string such as ``"30m"``, ``"1h"``, or ``"1h30m"``.

    Returns:
        Total seconds as an integer.  If the input is empty or contains no
        recognisable pairs, the function returns **3600** (1 hour) as a safe
        default for moderation timeouts.
    """
    text = text.strip().lower()
    if not text:
        return _DEFAULT_SECONDS

    total = 0
    matches = _DURATION_RE.findall(text)
    if not matches:
        return _DEFAULT_SECONDS

    for value_str, unit in matches:
        total += int(value_str) * _UNIT_TO_SECONDS[unit]

    return total


def parse_duration_strict(text: str) -> int | None:
    """Strict comma-prefixed duration parser for the ,12h timer.

    Matches ``^,\\s*(\\d+\\s*[smhdwy])+$`` (case-insensitive).  On match
    returns summed seconds (w=7d, y=365d).  On any non-match returns
    ``None`` — never the 3600 fallback that :func:`parse_duration` uses.
    """
    raw = text.strip()
    if not raw or not _STRICT_RE.match(raw):
        return None
    # Strip leading comma and parse pairs case-insensitively.
    body = raw.lstrip(",").strip()
    # Remove the leading spaces after comma already validated by _STRICT_RE.
    # _STRICT_FIND_RE finds each (number)(unit) allowing spaces between.
    pairs = _STRICT_FIND_RE.findall(body)
    if not pairs:
        return None
    total = 0
    for value_str, unit in pairs:
        unit_lower = unit.lower()
        secs = _STRICT_UNIT_TO_SECONDS.get(unit_lower)
        if secs is None:
            return None
        total += int(value_str) * secs
    return total


def parse_duration_optional(text: str) -> int | None:
    """Parse a human duration string to seconds, or None if unparseable.

    Reuses :data:`_UNIT_TO_SECONDS` (s/m/h/d) and :data:`_DURATION_RE`.
    Returns ``None`` when the input contains no recognisable
    ``(number)(unit)`` pairs — unlike :func:`parse_duration` which falls
    back to 3600. Compound strings like ``"1h30m"`` are supported.

    NOTE: This module is distinct from :mod:`bot.utils.timeparse` (DB
    timestamp → datetime parsing). They serve different domains and MUST
    NOT be merged — DO NOT MERGE with ``timeparse.py``. See
    ``bot/utils/timeparse.py`` for the separate domain.
    """
    raw = text.strip().lower() if isinstance(text, str) else ""
    if not raw:
        return None
    matches = _DURATION_RE.findall(raw)
    if not matches:
        return None
    total = 0
    for value_str, unit in matches:
        total += int(value_str) * _UNIT_TO_SECONDS[unit]
    return total


def format_remaining(seconds: int, *, guild_id: str | int | None = None) -> str:
    """Format *seconds* as a localized human duration string.

    Uses :func:`bot.core.i18n.t` for localization via the guild's
    configured language.
    """
    # Resolve a localized compact string. Use generic keys so tests
    # don't depend on exact locale payload shape — fall back to 12h-style.
    return _format_compact(seconds, guild_id)


def _format_compact(seconds: int, guild_id: str | int | None) -> str:
    """Compact duration formatter (e.g. 43200 -> '12h')."""
    # Prefer locale-aware keys if present, else produce 12h-style.
    # The spec requires "12h"-style via t() — generate via units.
    parts: list[str] = []
    remaining = seconds
    for unit, secs in (("day", 86400), ("hour", 3600), ("minute", 60), ("second", 1)):
        if remaining >= secs:
            count = remaining // secs
            remaining %= secs
            # Localized unit label: try key tickets.timer.unit_{unit}; fall back
            # to the compact letter when the key is missing.
            label = t(guild_id, f"tickets.timer.unit_{unit}")
            # t() falls back to raw key when missing; detect and use compact.
            if label.startswith("tickets.timer"):
                label = unit[0]
            parts.append(f"{count}{label}")
            if len(parts) >= 2:
                break
    if not parts:
        return "0s"
    # Ensure the RED test's "12" substring holds; compact is already 12h-style.
    return " ".join(parts)
