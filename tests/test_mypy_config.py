"""Validate pyproject.toml mypy configuration for tooling-rigor change.

Covers the pyproject-toml-qa-config spec scenarios:
    - strict = true enabled
    - No global disable_error_code
    - Per-file overrides exist for known debt modules (bot.bot)
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PYPROJECT = _PROJECT_ROOT / "pyproject.toml"


@pytest.fixture()
def pyproject() -> dict:
    """Load pyproject.toml as a dict."""
    with open(_PYPROJECT, "rb") as f:
        return tomllib.load(f)


@pytest.fixture()
def mypy_config(pyproject: dict) -> dict:
    """Extract [tool.mypy] section."""
    return pyproject["tool"]["mypy"]


@pytest.fixture()
def mypy_overrides(pyproject: dict) -> list[dict]:
    """Extract [[tool.mypy.overrides]] list."""
    return pyproject["tool"]["mypy"].get("overrides", [])


# ---------------------------------------------------------------------------
# Scenario: Mypy strict mode enabled
# ---------------------------------------------------------------------------


class TestMypyStrict:
    """[tool.mypy] MUST have strict = true."""

    def test_strict_is_true(self, mypy_config: dict) -> None:
        """strict MUST be True."""
        assert mypy_config.get("strict") is True, f"Expected mypy strict=true, got {mypy_config.get('strict')}"


# ---------------------------------------------------------------------------
# Scenario: attr-defined suppressed per-file only
# ---------------------------------------------------------------------------


class TestMypyNoGlobalDisable:
    """Mypy MUST NOT have a project-wide disable_error_code."""

    def test_no_global_disable_error_code(self, mypy_config: dict) -> None:
        """Global disable_error_code MUST NOT be present."""
        assert "disable_error_code" not in mypy_config, (
            f"Global disable_error_code found: {mypy_config.get('disable_error_code')}"
        )


class TestMypyOverrides:
    """Per-file overrides MUST exist for known debt modules."""

    def test_bot_bot_override_exists(self, mypy_overrides: list[dict]) -> None:
        """An override for bot.bot MUST exist."""
        bot_bot_overrides = [o for o in mypy_overrides if o.get("module") == "bot.bot"]
        assert len(bot_bot_overrides) >= 1, (
            f"No override found for 'bot.bot'. Existing overrides: {[o.get('module') for o in mypy_overrides]}"
        )

    def test_bot_bot_override_disables_attr_defined(self, mypy_overrides: list[dict]) -> None:
        """bot.bot override MUST disable attr-defined error code."""
        bot_bot_overrides = [o for o in mypy_overrides if o.get("module") == "bot.bot"]
        assert len(bot_bot_overrides) >= 1, "No override for bot.bot"
        override = bot_bot_overrides[0]
        disabled = override.get("disable_error_code", [])
        assert "attr-defined" in disabled, f"bot.bot override must disable 'attr-defined', got: {disabled}"
