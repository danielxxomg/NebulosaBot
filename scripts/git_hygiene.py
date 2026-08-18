"""Git hygiene helpers — rejects ambiguous origin/SHA before prune/diff.

Threat matrix: Git repository selection — explicit origin and SHA/ref.
Wrong path aborts before any destructive prune. Pure helpers so they
are unit-testable without spawning git.
"""

from __future__ import annotations

import re

# Minimal explicit SHA length — 7 matches the baseline f83e767 / 8cb5674
# used as archive diff anchors while rejecting trivially ambiguous short refs.
_MIN_SHA_LEN = 7
_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")


def assert_explicit_origin(origin: str) -> str:
    """Validate that the git remote is explicitly ``origin``.

    Rejects empty, whitespace-padded, partial, or non-origin remotes so
    prune/diff cannot silently target the wrong remote. Returns the
    canonical ``origin`` on success.
    """
    if origin != "origin":
        raise ValueError(f"origin must be explicit 'origin', got {origin!r}")
    return origin


def assert_explicit_sha(sha: str) -> str:
    """Validate that a SHA/ref is explicit and unambiguous.

    Requires at least 7 hex characters with no surrounding whitespace.
    Returns the lower-cased SHA on success so callers use a canonical form.
    """
    if not sha or sha != sha.strip():
        raise ValueError(f"SHA/ref must be explicit non-empty without surrounding whitespace, got {sha!r}")
    if len(sha) < _MIN_SHA_LEN:
        raise ValueError(f"SHA/ref too short (<{_MIN_SHA_LEN}) and therefore ambiguous, got {sha!r}")
    if not _HEX_RE.match(sha):
        raise ValueError(f"SHA/ref must be hex, got {sha!r}")
    return sha.lower()


def validate_git_prune_target(origin: str, sha: str) -> bool:
    """Validate a prune/diff target — origin first, then SHA.

    Ordering is deterministic so callers get the origin error when both are
    ambiguous, matching the threat matrix abort-before-prune contract.
    """
    assert_explicit_origin(origin)
    assert_explicit_sha(sha)
    return True
