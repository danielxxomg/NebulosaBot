"""CrashReportService — single writer for crash_report (data-retention F4).

Only called from unhandled branches of on_app_command_error /
on_command_error and a root-level CRITICAL logging handler. Business
ERROR logs never reach it (threshold CRITICAL; explicit call sites
enumerated in design D3).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bot.core.database import Database

logger = logging.getLogger(__name__)


class CrashReportService:
    """Persist crash_report rows for unhandled exceptions only.

    Production call sites are enumerated: the final else branch of
    on_app_command_error and on_command_error (unexpected errors) plus
    a CRITICAL logging handler. CheckFailure / MissingPermissions /
    business ERROR logs MUST NOT call this service.
    """

    def __init__(self, db: Database | Any) -> None:
        self._db = db

    async def record(
        self,
        *,
        guild_id: str | None,
        command: str | None,
        traceback_text: str,
    ) -> None:
        """Insert one crash_report row (unhandled scope only).

        Args:
            guild_id: Guild snowflake string or None (DM / unknown).
            command: Qualified command name or None.
            traceback_text: Full traceback / exception text.

        The row is inserted via Database.insert_crash_report (falls back
        to direct table insert if the helper is not yet wired). Failures
        are logged at WARNING and never propagate — crash reporting must
        not break the error handler.
        """
        try:
            # Prefer a dedicated helper if the DB facade exposes it.
            insert_fn = getattr(self._db, "insert_crash_report", None)
            if callable(insert_fn):
                await insert_fn(
                    guild_id=guild_id,
                    command=command,
                    traceback_text=traceback_text,
                )
                return
            # Fallback: direct table insert via the underlying client.
            client = getattr(self._db, "_client", None)
            if client is not None:
                row: dict[str, Any] = {
                    "guildId": guild_id,
                    "command": command,
                    "traceback": traceback_text,
                }
                await client.table("crash_report").insert(row).execute()
                # Echo suppression hook if present.
                on_write = getattr(self._db, "_on_write", None)
                if callable(on_write):
                    try:
                        await on_write("crash_report", row.get("id", ""))  # type: ignore[arg-type]
                    except Exception:  # noqa: BLE001 -- best-effort echo suppression
                        pass
                return
            logger.warning("CrashReportService: no insert path available (db has no _client)")
        except Exception:  # noqa: BLE001 -- crash reporting never propagates
            logger.warning("Failed to insert crash_report row", exc_info=True)
