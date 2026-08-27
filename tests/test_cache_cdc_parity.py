"""CDC parity test — docs must equal handlers, deferred labeled (S5.1).

Spec: cache-layer "Documentation matches CDC reality".

- Documented set (from bot/core/cache.py Realtime-invalidated line) == frozenset(SUBSCRIBED_TABLES) both directions.
- Any mention of member/economy outside the active claims line must sit under an explicit
  "Deferred:" marker, never as an active guarantee. Drift fails.
"""

from __future__ import annotations

import re
from pathlib import Path

from bot.core.realtime import SUBSCRIBED_TABLES

REPO_ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = REPO_ROOT / "bot" / "core" / "cache.py"

_CLAIM_RE = re.compile(r"Realtime-invalidated entities:\s*(.+)", re.IGNORECASE)


def _load_docstring() -> str:
    text = CACHE_PATH.read_text(encoding="utf-8")
    # Module docstring is the first triple-quoted string
    m = re.search(r'"""(.*?)"""', text, re.DOTALL)
    assert m is not None, "bot/core/cache.py must have a module docstring"
    return m.group(1)


def _parse_claimed(doc: str) -> set[str]:
    m = _CLAIM_RE.search(doc)
    assert m is not None, "cache.py docstring must contain 'Realtime-invalidated entities:' claim block"
    raw = m.group(1)
    # Strip possible trailing comment / deferred marker on same line
    # Take only up to newline, split by comma
    # Remove parenthetical, etc.
    # Example: "guild, greeting_config, ticket, ticket_note, member, economy_config"
    # Allow optional "Deferred:" suffix on same line — ignore after ';' or '|'
    raw = raw.split("\n")[0]
    # Remove any trailing parenthetical
    raw = raw.split("(")[0]
    raw = raw.split(";")[0]
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    # Normalize to bare table names
    return {p.strip().strip('"').strip("'") for p in parts}


def test_documented_streams_equal_registered_handlers() -> None:
    """Documented set must equal SUBSCRIBED_TABLES both directions.

    Drift in either direction fails: undocumented handler or documented-but-unregistered.
    """
    doc = _load_docstring()
    documented = _parse_claimed(doc)
    subscribed = set(SUBSCRIBED_TABLES)
    missing_in_docs = subscribed - documented
    extra_in_docs = documented - subscribed
    assert not missing_in_docs, f"Handlers not documented: {sorted(missing_in_docs)}"
    assert not extra_in_docs, f"Documented streams not in SUBSCRIBED_TABLES: {sorted(extra_in_docs)}"
    # Also enforce frozenset equality both directions as one assertion for message
    assert documented == subscribed, f"Documented {documented} != subscribed {subscribed}"


def test_deferred_paths_labeled_explicitly() -> None:
    """Any member/economy mention outside the active claims line must be under Deferred:.

    Until member/economy ships, docs must label them deferred; after ship they must NOT
    appear as deferred active guarantees. This test enforces that any stray mention of
    "member" or "economy" outside the Realtime line sits under an explicit Deferred: marker.
    """
    doc = _load_docstring()
    # Remove the Realtime line itself so its member/economy entries are not counted as stray
    doc_without_claim = _CLAIM_RE.sub("", doc)
    # Find stray mentions (case-insensitive for economy_config, member)
    # We look for the literal table names
    stray_members = []
    for tbl in ("member", "economy_config", "economy"):
        # word boundary search
        if re.search(rf"\b{re.escape(tbl)}\b", doc_without_claim, re.IGNORECASE):
            stray_members.append(tbl)
    if not stray_members:
        return  # No stray mention — passes vacuously (active claims are the only place)
    # Stray mentions exist -> doc must contain an explicit Deferred: marker
    assert "Deferred:" in doc, (
        f"Stray member/economy mention {stray_members} found outside active claims "
        "but no 'Deferred:' marker in docstring"
    )
    # Ensure stray mentions appear only after Deferred:
    deferred_idx = doc.index("Deferred:")
    # Check that each stray mention's first occurrence after removal is after Deferred
    # i.e., no stray before Deferred
    before_deferred = doc[:deferred_idx]
    before_without_claim = _CLAIM_RE.sub("", before_deferred)
    for tbl in stray_members:
        assert not re.search(rf"\b{re.escape(tbl)}\b", before_without_claim, re.IGNORECASE), (
            f"'{tbl}' appears before Deferred: marker — must sit under Deferred:"
        )


def test_doc_drift_fails_on_mismatch() -> None:
    """Sanity: parsing must be deterministic — documented set is exactly subscribed."""
    doc = _load_docstring()
    documented = _parse_claimed(doc)
    subscribed = set(SUBSCRIBED_TABLES)
    # Both directions already checked, but this test documents the drift-fail requirement
    assert documented == subscribed, f"Drift: documented {documented} != subscribed {subscribed}"
