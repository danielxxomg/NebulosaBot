"""Validate pyproject.toml mypy → ty migration (PR2 qa-modernization).

mypy was replaced by ty in PR2. When [tool.mypy] is absent, these tests skip
(PR2 2.3). See tests/test_pr2_ty_replaces_mypy.py for the new ty assertions.
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
    """Extract [tool.mypy] section — skip when mypy removed (PR2 ty replaces mypy)."""
    tool = pyproject.get("tool", {})
    if "mypy" not in tool:
        pytest.skip("mypy removed — ty replaces mypy (PR2 qa-modernization 2.3)")
    return tool["mypy"]


@pytest.fixture()
def mypy_overrides(pyproject: dict) -> list[dict]:
    """Extract [[tool.mypy.overrides]] list — skip when mypy removed."""
    tool = pyproject.get("tool", {})
    if "mypy" not in tool:
        pytest.skip("mypy removed — ty replaces mypy (PR2 qa-modernization 2.3)")
    return tool["mypy"].get("overrides", [])


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
    """Per-file overrides MUST exist only for known tech-debt modules."""

    def test_no_bot_bot_override(self, mypy_overrides: list[dict]) -> None:
        """bot.bot override MUST NOT exist — attr-defined resolved via isinstance narrowing."""
        bot_bot_overrides = [o for o in mypy_overrides if o.get("module") == "bot.bot"]
        assert len(bot_bot_overrides) == 0, f"bot.bot override still present — remove it: {bot_bot_overrides}"

    def test_no_bot_core_override(self, mypy_overrides: list[dict]) -> None:
        """bot.core.* override MUST NOT exist — modules pass strict without suppression."""
        core_overrides = [o for o in mypy_overrides if o.get("module") == "bot.core.*"]
        assert len(core_overrides) == 0, f"bot.core.* override still present — remove it: {core_overrides}"

    def test_no_bot_listeners_override(self, mypy_overrides: list[dict]) -> None:
        """bot.listeners.* override MUST NOT exist — modules pass strict without suppression."""
        listeners_overrides = [o for o in mypy_overrides if o.get("module") == "bot.listeners.*"]
        assert len(listeners_overrides) == 0, (
            f"bot.listeners.* override still present — remove it: {listeners_overrides}"
        )

    def test_only_tech_debt_overrides_remain(self, mypy_overrides: list[dict]) -> None:
        """Only bot.cogs.* and tests.* overrides MUST remain after type-strict cleanup."""
        modules = sorted(str(o.get("module", "")) for o in mypy_overrides)
        assert modules == ["bot.cogs.*", "tests.*"], f"Unexpected mypy override set: {modules}"


# ---------------------------------------------------------------------------
# Scenario: bot.cogs.* override narrowed to untyped-decorator only
# ---------------------------------------------------------------------------


class TestMypyCogsOverride:
    """bot.cogs.* override MUST exist and disable ONLY untyped-decorator."""

    def test_cogs_wildcard_override_exists(self, mypy_overrides: list[dict]) -> None:
        """An override for bot.cogs.* MUST exist."""
        cogs_overrides = [o for o in mypy_overrides if o.get("module") == "bot.cogs.*"]
        assert len(cogs_overrides) >= 1, (
            f"No override found for 'bot.cogs.*'. Existing overrides: {[o.get('module') for o in mypy_overrides]}"
        )

    def test_cogs_override_disables_only_untyped_decorator(self, mypy_overrides: list[dict]) -> None:
        """bot.cogs.* override MUST disable ONLY untyped-decorator (+ arg-type for hybrid stubs)."""
        cogs_overrides = [o for o in mypy_overrides if o.get("module") == "bot.cogs.*"]
        assert len(cogs_overrides) >= 1, "No override for bot.cogs.*"
        override = cogs_overrides[0]
        disabled = override.get("disable_error_code", [])
        # PR2: hybrid_command + NebulosaContext still needs arg-type/unused-ignore for discord.py stubs
        allowed = {"untyped-decorator", "arg-type", "unused-ignore"}
        assert set(disabled).issubset(allowed) and "untyped-decorator" in disabled, (
            f"bot.cogs.* override must be subset of {allowed} including untyped-decorator, got: {disabled}"
        )


# ---------------------------------------------------------------------------
# Scenario: bot.services.* wildcard override removed (type-strict-services)
# ---------------------------------------------------------------------------


class TestMypyNoServicesWildcard:
    """No override MUST target bot.services.* — services must be strict-typed."""

    def test_no_services_wildcard_override(self, mypy_overrides: list[dict]) -> None:
        """bot.services.* override MUST NOT exist."""
        services_overrides = [o for o in mypy_overrides if o.get("module") == "bot.services.*"]
        assert len(services_overrides) == 0, f"bot.services.* override still present — remove it: {services_overrides}"


# ---------------------------------------------------------------------------
# Scenario: bot.models.* wildcard override removed (type-strict-models)
# ---------------------------------------------------------------------------


class TestMypyNoModelsWildcard:
    """No override MUST target bot.models.* — models must be strict-typed."""

    def test_no_models_wildcard_override(self, mypy_overrides: list[dict]) -> None:
        """bot.models.* override MUST NOT exist."""
        models_overrides = [o for o in mypy_overrides if o.get("module") == "bot.models.*"]
        assert len(models_overrides) == 0, f"bot.models.* override still present — remove it: {models_overrides}"
