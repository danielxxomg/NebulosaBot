"""Structural guard — infraction_db.get_expired_tempbans MUST NOT suppress(Exception).

GGA C Round 4 blocker 2: ``get_expired_tempbans`` wrapped the duck-typed
``neq_fn("expiresAt", None)`` probe in ``contextlib.suppress(Exception)`` so
fake builders without a working ``neq`` would silently skip the filter.
That hides real builder errors behind a broad suppress — AGENTS.md rejects
bare/broad ``except`` and mandates specific exception handling.  The
``neq`` call must run directly behind the existing ``callable(neq_fn)``
guard and let any error propagate.

This guard proves the suppression is gone:
    - NO ``contextlib.suppress`` in infraction_db.py.
    - NO ``import contextlib`` left over.
"""

from __future__ import annotations

from pathlib import Path

_DB_PATH = Path(__file__).resolve().parent.parent / "bot" / "core" / "db" / "infraction_db.py"


def _db_source() -> str:
    if not _DB_PATH.exists():
        return ""
    return _DB_PATH.read_text(encoding="utf-8")


class TestInfractionDbNoSuppress:
    """get_expired_tempbans must propagate builder errors, not suppress them."""

    def test_no_contextlib_suppress_in_infraction_db(self) -> None:
        src = _db_source()
        assert src, "bot/core/db/infraction_db.py not found"
        assert "contextlib.suppress" not in src, (
            "bot/core/db/infraction_db.py must not use contextlib.suppress — "
            "builder errors from neq must propagate behind the callable() "
            "guard, not be swallowed by a broad suppress."
        )

    def test_no_contextlib_import_in_infraction_db(self) -> None:
        src = _db_source()
        assert src, "bot/core/db/infraction_db.py not found"
        assert "import contextlib" not in src, (
            "bot/core/db/infraction_db.py must not import contextlib — the "
            "suppress usage was the only consumer and must be removed with it."
        )
