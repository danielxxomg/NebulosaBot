"""Ticket reference parser — pure utility for /reopen ticket:#0003 / UUID refs.

Moved from bot.services.ticket_invariants so that utils (ticket_helpers)
can import from core without violating the layered architecture
(utils → services is forbidden; utils → core is allowed).

Re-exported from bot.services.ticket_invariants for blast-radius zero:
existing importers (ticket_service, lifecycle, repair + 5 test files)
continue to import from services unchanged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TicketRef:
    """A parsed /reopen ticket reference — exactly one of *number*/*uuid* set.

    The cog resolves a *number* via ``Database.get_ticket_by_number(guild_id, n)``
    and a *uuid* via ``Database.get_ticket(id)`` plus a guild-scope check.
    """

    number: int | None = None
    uuid: str | None = None


# UUID v4-ish (we do not enforce version — any 8-4-4-4-12 hex block).
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
# A run of digits, optionally prefixed with '#'.
_NUMBER_RE = re.compile(r"^#?(\d+)$")


def parse_ticket_ref(ref_str: str | None) -> TicketRef | None:
    """Parse a ``/reopen`` ticket reference into a :class:`TicketRef`.

    Accepts (after stripping an optional ``ticket:`` prefix):
        - ``#0003`` or ``0003`` → ``TicketRef(number=3)``
        - a UUID (``8-4-4-4-12`` hex) → ``TicketRef(uuid=...)``

    Returns ``None`` for empty/whitespace input or unparseable strings so the
    caller (``/reopen`` cog) can distinguish "no arg" (legacy channel lookup)
    from "bad arg" (user-facing error).

    The literal guidance text ``/reopen ticket:#0003`` is valid: the slash
    option is ``ticket_ref`` whose value ``ticket:#0003`` the parser strips to
    ``#0003`` → ``number=3``. A bare ``#0003`` value also parses to ``3``.
    """
    if ref_str is None:
        return None
    value = ref_str.strip()
    if not value:
        return None
    # Strip an optional 'ticket:' prefix (case-insensitive).
    if value.lower().startswith("ticket:"):
        value = value[len("ticket:") :]
    value = value.strip()
    if not value:
        return None
    # UUID?
    if _UUID_RE.match(value):
        return TicketRef(uuid=value.lower())
    # #0003 / 0003?
    num_match = _NUMBER_RE.match(value)
    if num_match is not None:
        return TicketRef(number=int(num_match.group(1)))
    return None
