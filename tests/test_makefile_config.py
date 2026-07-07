"""Validate Makefile for tooling-rigor change.

Covers the makefile-dx spec scenarios:
    - make cov target passes --cov-fail-under=75
    - make test target passes --cov-fail-under=75
"""

from __future__ import annotations

from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_MAKEFILE = _PROJECT_ROOT / "Makefile"


@pytest.fixture()
def makefile_content() -> str:
    """Read Makefile content."""
    return _MAKEFILE.read_text()


@pytest.fixture()
def test_target(makefile_content: str) -> str:
    """Extract the 'test:' target recipe."""
    return _extract_target(makefile_content, "test")


@pytest.fixture()
def cov_target(makefile_content: str) -> str:
    """Extract the 'cov:' target recipe."""
    return _extract_target(makefile_content, "cov")


# ---------------------------------------------------------------------------
# Scenario: make cov enforces 75% gate
# ---------------------------------------------------------------------------


class TestMakefileCov:
    """make cov MUST pass --cov-fail-under=75."""

    def test_cov_target_has_fail_under_75(self, cov_target: str) -> None:
        """cov target MUST include --cov-fail-under=75."""
        assert "--cov-fail-under=75" in cov_target, (
            f"--cov-fail-under=75 not in cov target:\n{cov_target}"
        )

    def test_cov_target_has_cov_report(self, cov_target: str) -> None:
        """cov target MUST include --cov-report for output."""
        assert "--cov-report" in cov_target, (
            f"--cov-report not in cov target:\n{cov_target}"
        )


# ---------------------------------------------------------------------------
# Scenario: make test also enforces the gate
# ---------------------------------------------------------------------------


class TestMakefileTest:
    """make test MUST pass --cov-fail-under=75."""

    def test_test_target_has_fail_under_75(self, test_target: str) -> None:
        """test target MUST include --cov-fail-under=75."""
        assert "--cov-fail-under=75" in test_target, (
            f"--cov-fail-under=75 not in test target:\n{test_target}"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_target(makefile: str, target_name: str) -> str:
    """Extract the recipe lines for a given Makefile target.

    Returns the concatenated recipe lines (without leading tabs).
    """
    lines = makefile.splitlines()
    in_target = False
    recipe_lines: list[str] = []

    for line in lines:
        # Detect target line: "target_name:" at start of line (no leading space)
        if line.startswith(f"{target_name}:"):
            in_target = True
            continue
        if in_target:
            if line.startswith("\t"):
                recipe_lines.append(line.strip())
            elif line.strip() == "":
                continue  # skip blank lines within target
            else:
                break  # next target or non-recipe line

    return "\n".join(recipe_lines)
