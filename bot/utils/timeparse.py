"""Timestamp parser — converts DB values (str/datetime/None) to datetime.

Used by economy_service to safely parse lastXpGain, lastDaily, and
lastDailyReset timestamps regardless of whether Supabase returns them
as datetime objects or ISO-8601 strings.
"""

from __future__ import annotations

from datetime import datetime


def _to_datetime(value: datetime | str | None) -> datetime | None:
    """Return a parsed datetime, or None for None/invalid DB timestamp values.

    Args:
        value: A datetime object, ISO-8601 string, or None.

    Returns:
        The parsed datetime, or None if the value is None or unparseable.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None
