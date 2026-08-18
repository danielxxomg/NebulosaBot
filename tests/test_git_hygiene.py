"""Tests for git hygiene helper — rejects ambiguous origin/SHA.

PR1a task 1.1: RED git helper rejects ambiguous origin/SHA.
Threat matrix: Git repository selection — explicit origin and SHA/ref.
Wrong path aborts before prune.

Strict TDD: write failing test first, then minimal impl.
"""

from __future__ import annotations

import pytest

# These imports will FAIL initially (RED) — module does not exist yet.
from scripts.git_hygiene import assert_explicit_origin, assert_explicit_sha, validate_git_prune_target


class TestOriginHygiene:
    """Origin MUST be explicit 'origin' — any ambiguity aborts."""

    def test_valid_origin_passes(self) -> None:
        """Explicit 'origin' is accepted."""
        assert assert_explicit_origin("origin") == "origin"

    def test_empty_origin_rejected(self) -> None:
        """Empty origin is ambiguous — must raise."""
        with pytest.raises(ValueError, match="origin"):
            assert_explicit_origin("")

    def test_whitespace_origin_rejected(self) -> None:
        """Whitespace-padded origin is ambiguous — must raise."""
        with pytest.raises(ValueError, match="origin"):
            assert_explicit_origin(" origin ")

    def test_wrong_remote_rejected(self) -> None:
        """Non-origin remote is ambiguous — must raise."""
        with pytest.raises(ValueError, match="origin"):
            assert_explicit_origin("upstream")

    def test_origin_prefix_rejected(self) -> None:
        """Partial origin like 'orig' is ambiguous — must raise."""
        with pytest.raises(ValueError, match="origin"):
            assert_explicit_origin("orig")


class TestShaHygiene:
    """SHA/ref MUST be explicit — ambiguous short or non-hex aborts."""

    def test_valid_full_sha_passes(self) -> None:
        """Full 40-char hex SHA is accepted."""
        full = "f83e767f920d9aa5defb1b5a2d5178f1ab000d65"
        assert assert_explicit_sha(full) == full.lower()

    def test_valid_short_sha_7_passes(self) -> None:
        """7-char hex SHA (baseline f83e767) is accepted as minimal explicit."""
        assert assert_explicit_sha("f83e767") == "f83e767"
        assert assert_explicit_sha("8cb5674") == "8cb5674"

    def test_ambiguous_short_sha_rejected(self) -> None:
        """SHA shorter than 7 is ambiguous — must raise."""
        with pytest.raises(ValueError, match="SHA"):
            assert_explicit_sha("abc")

    def test_non_hex_sha_rejected(self) -> None:
        """Non-hex chars are ambiguous — must raise."""
        with pytest.raises(ValueError, match="SHA"):
            assert_explicit_sha("zzzzzzz")

    def test_empty_sha_rejected(self) -> None:
        """Empty SHA is ambiguous — must raise."""
        with pytest.raises(ValueError, match="SHA"):
            assert_explicit_sha("")

    def test_sha_with_whitespace_rejected(self) -> None:
        """SHA with whitespace is ambiguous — must raise."""
        with pytest.raises(ValueError, match="SHA"):
            assert_explicit_sha(" f83e767 ")


class TestPruneTargetValidation:
    """Combined origin+ref validation for prune/diff — abort on ambiguity."""

    def test_valid_prune_target_passes(self) -> None:
        """Explicit origin and explicit ref together pass."""
        assert validate_git_prune_target("origin", "f83e767f920d9aa5defb1b5a2d5178f1ab000d65") is True

    def test_ambiguous_origin_in_prune_target_rejected(self) -> None:
        """Ambiguous origin in prune target must raise."""
        with pytest.raises(ValueError, match="origin"):
            validate_git_prune_target("upstream", "f83e767")

    def test_ambiguous_sha_in_prune_target_rejected(self) -> None:
        """Ambiguous SHA in prune target must raise."""
        with pytest.raises(ValueError, match="SHA"):
            validate_git_prune_target("origin", "abc")

    def test_both_ambiguous_rejected_origin_first(self) -> None:
        """Both ambiguous — origin error surfaces first (deterministic)."""
        with pytest.raises(ValueError, match="origin"):
            validate_git_prune_target("", "")
