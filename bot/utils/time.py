"""Duration parser — converts human-readable strings to seconds.

Used by SentinelCog to parse moderation timeout durations such as
"1h", "30m", "2d", or compound like "1h30m".

Returns 3600 (1 hour) for any unparseable input so mute commands
degrade gracefully when the user provides a malformed duration.
"""

from __future__ import annotations

import re

# Map single-letter suffix to seconds.
_UNIT_TO_SECONDS: dict[str, int] = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
}

# Matches one or more (number)(unit) pairs, e.g. "1h30m", "2d", "30s".
_DURATION_RE = re.compile(r"(\d+)([smhd])")

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
