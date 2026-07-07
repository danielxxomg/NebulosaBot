"""Validate pyproject.toml ruff configuration for tooling-rigor change.

Covers the pyproject-toml-qa-config spec scenarios:
    - Ruff select includes all 14 new rule groups
    - max-complexity = 15 in [tool.ruff.mccabe]
    - per-file-ignores suppress S101, ARG, T20 in tests/
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PYPROJECT = _PROJECT_ROOT / "pyproject.toml"

# The 14 new rule groups required by the tooling-rigor spec
_EXPECTED_NEW_GROUPS = [
    "S",      # bandit/security
    "C4",     # comprehensions
    "C90",    # mccabe complexity
    "RET",    # return
    "T20",    # print
    "ARG",    # unused arguments
    "DTZ",    # datetime timezone
    "EM",     # errmsg
    "T10",    # debugger
    "TRY",    # tryceratops
    "RSE",    # raise
    "FLY",    # flynt
    "PERF",   # perflint
    "FURB",   # refurb
]


@pytest.fixture()
def pyproject() -> dict:
    """Load pyproject.toml as a dict."""
    with open(_PYPROJECT, "rb") as f:
        return tomllib.load(f)


@pytest.fixture()
def ruff_select(pyproject: dict) -> list[str]:
    """Extract the ruff lint select list."""
    return pyproject["tool"]["ruff"]["lint"]["select"]


@pytest.fixture()
def ruff_per_file_ignores(pyproject: dict) -> dict[str, list[str]]:
    """Extract [tool.ruff.lint.per-file-ignores]."""
    return pyproject["tool"]["ruff"]["lint"]["per-file-ignores"]


# ---------------------------------------------------------------------------
# Scenario: New rule groups enforced
# ---------------------------------------------------------------------------


class TestRuffSelectGroups:
    """Ruff select MUST include all 14 new rule groups."""

    @pytest.mark.parametrize("group", _EXPECTED_NEW_GROUPS)
    def test_select_includes_new_group(self, ruff_select: list[str], group: str) -> None:
        """select MUST contain {group}."""
        assert group in ruff_select, (
            f"Ruff select missing required group '{group}'. "
            f"Current select: {ruff_select}"
        )

    def test_select_includes_original_groups(self, ruff_select: list[str]) -> None:
        """select MUST still include the original 9 groups (E, W, F, I, N, UP, B, SIM, RUF)."""
        original = ["E", "W", "F", "I", "N", "UP", "B", "SIM", "RUF"]
        for group in original:
            assert group in ruff_select, (
                f"Ruff select missing original group '{group}'. "
                f"Current select: {ruff_select}"
            )


# ---------------------------------------------------------------------------
# Scenario: McCabe complexity limit enforced
# ---------------------------------------------------------------------------


class TestRuffMcCabe:
    """[tool.ruff.mccabe] MUST set max-complexity = 15."""

    def test_max_complexity_is_15(self, pyproject: dict) -> None:
        """max-complexity MUST be 15."""
        mccabe = pyproject["tool"]["ruff"]["lint"].get("mccabe", {})
        assert mccabe.get("max-complexity") == 15, (
            f"Expected max-complexity=15, got {mccabe.get('max-complexity')}"
        )


# ---------------------------------------------------------------------------
# Scenario: Test files exempt from assert and print rules
# ---------------------------------------------------------------------------


class TestRuffTestIgnores:
    """tests/ MUST have per-file ignores for S101, ARG, T20."""

    def test_tests_dir_has_ignores(self, ruff_per_file_ignores: dict[str, list[str]]) -> None:
        """A tests/**/*.py key MUST exist in per-file-ignores."""
        # Find the key that matches tests
        tests_key = None
        for key in ruff_per_file_ignores:
            if "tests" in key:
                tests_key = key
                break
        assert tests_key is not None, (
            f"No tests/ entry in per-file-ignores: {ruff_per_file_ignores}"
        )

    def test_tests_ignores_include_s101(self, ruff_per_file_ignores: dict[str, list[str]]) -> None:
        """tests/ ignores MUST include S101 (assert in tests)."""
        tests_ignores = self._get_tests_ignores(ruff_per_file_ignores)
        assert "S101" in tests_ignores, (
            f"S101 not in tests ignores: {tests_ignores}"
        )

    def test_tests_ignores_include_arg(self, ruff_per_file_ignores: dict[str, list[str]]) -> None:
        """tests/ ignores MUST include ARG rules."""
        tests_ignores = self._get_tests_ignores(ruff_per_file_ignores)
        assert "ARG" in tests_ignores, (
            f"ARG not in tests ignores: {tests_ignores}"
        )

    def test_tests_ignores_include_t20(self, ruff_per_file_ignores: dict[str, list[str]]) -> None:
        """tests/ ignores MUST include T20 rules."""
        tests_ignores = self._get_tests_ignores(ruff_per_file_ignores)
        assert "T20" in tests_ignores, (
            f"T20 not in tests ignores: {tests_ignores}"
        )

    @staticmethod
    def _get_tests_ignores(per_file_ignores: dict[str, list[str]]) -> list[str]:
        for key, val in per_file_ignores.items():
            if "tests" in key:
                return val
        return []
