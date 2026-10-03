"""Database connection validation and error scrubbing utilities.

Provides fail-closed verification of PostgreSQL connection URLs (enforcing
pooler markers and postgres schemes) and redaction of credentials and socket
paths from error messages and log outputs.
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass

REASON_OK = "ok"
REASON_EMPTY_URL = "empty_url"
REASON_INVALID_SCHEME = "invalid_scheme"
REASON_INVALID_FORMAT = "invalid_format"
REASON_MISSING_POOLER_MARKER = "missing_pooler_marker"

# Valid PostgreSQL URL schemes.
POSTGRES_SCHEMES: frozenset[str] = frozenset({"postgres", "postgresql"})

# Default standard PostgreSQL port.
POSTGRES_POOLER_PORT: int = 5432

# Pattern matching credentials in URIs (scheme://user:pass@ or scheme://user@).
_URI_CREDENTIALS_RE: re.Pattern[str] = re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://)([^@/\s]+)@")

# Pattern matching secret query parameters or key-value config assignments.
_SECRET_PARAMS_RE: re.Pattern[str] = re.compile(
    r"""(?i)\b((?:password|secret|token|key|api_key)\s*=\s*)(?:["'][^"'\s&;]+["']|[^\s&;'"\)]+)"""
)

# Pattern matching PostgreSQL Unix domain socket paths.
_UNIX_SOCKET_RE: re.Pattern[str] = re.compile(
    r"""(?i)(?:/[a-zA-Z0-9_.-]+)*/\.s\.PGSQL\.\d+|/(?:var/)?run/postgresql(?:/[a-zA-Z0-9_.-]+)*"""
)


@dataclass(frozen=True, slots=True)
class DBUrlValidationResult:
    """Structured result of database URL validation.

    Attributes:
        ok: True if the URL meets validation criteria, False otherwise.
        reason: Stable status code indicating validation outcome (never echoes the URL).
    """

    ok: bool
    reason: str


def validate_db_url(url: str | None) -> DBUrlValidationResult:
    """Validate a database connection URL without network I/O.

    Enforces fail-closed rules:
      1. Rejects absent, empty, or whitespace-only inputs.
      2. Rejects non-postgres schemes (must be ``postgres://`` or ``postgresql://``).
      3. Requires a pooler marker: either port 5432 or a hostname containing
         ``pooler`` or ``supabase`` (without assuming PostgreSQL server version).

    Args:
        url: Database URL string to inspect.

    Returns:
        DBUrlValidationResult: Structured result with boolean status and reason code.
        Never echoes or leaks the input URL.
    """
    if url is None or not isinstance(url, str):
        return DBUrlValidationResult(ok=False, reason=REASON_EMPTY_URL)

    cleaned = url.strip()
    if not cleaned:
        return DBUrlValidationResult(ok=False, reason=REASON_EMPTY_URL)

    try:
        parsed = urllib.parse.urlsplit(cleaned)
    except Exception:  # noqa: BLE001 -- malformed URL parsing failure
        return DBUrlValidationResult(ok=False, reason=REASON_INVALID_FORMAT)

    scheme = parsed.scheme.lower()
    if scheme not in POSTGRES_SCHEMES:
        return DBUrlValidationResult(ok=False, reason=REASON_INVALID_SCHEME)

    try:
        port = parsed.port
    except ValueError:
        return DBUrlValidationResult(ok=False, reason=REASON_INVALID_FORMAT)

    hostname = (parsed.hostname or "").lower()

    has_host_marker = "pooler" in hostname or "supabase" in hostname
    has_port_marker = port == POSTGRES_POOLER_PORT

    if not (has_host_marker or has_port_marker):
        return DBUrlValidationResult(ok=False, reason=REASON_MISSING_POOLER_MARKER)

    return DBUrlValidationResult(ok=True, reason=REASON_OK)


def scrub_error(text: str) -> str:
    """Redact credentials and socket paths from error and log messages.

    Redacts:
      - URI credentials (e.g. ``scheme://user:pass@host``).
      - Secret query parameters and key-value options (``password``, ``secret``,
        ``token``, ``key``, ``api_key``).
      - PostgreSQL Unix domain socket paths (e.g. ``/var/run/postgresql/.s.PGSQL.5432``).

    Args:
        text: Raw error or log message string.

    Returns:
        str: Message safe for logs and exceptions with sensitive details redacted.
    """
    if not text:
        return ""

    # Redact URI credentials
    scrubbed = _URI_CREDENTIALS_RE.sub(r"\1***:***@", text)

    # Redact secret parameters / key-values
    scrubbed = _SECRET_PARAMS_RE.sub(r"\1[REDACTED]", scrubbed)

    # Redact Unix domain socket paths
    return _UNIX_SOCKET_RE.sub("[REDACTED_SOCKET]", scrubbed)
