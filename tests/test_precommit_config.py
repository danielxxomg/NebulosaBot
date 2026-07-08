"""Validate .pre-commit-config.yaml for tooling-rigor change.

Covers the pre-commit-config-file spec scenarios:
    - Hook order: ruff check → ruff format → mypy
    - files pattern: ^(bot/|tests/) on ruff and mypy hooks
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PRECOMMIT = _PROJECT_ROOT / ".pre-commit-config.yaml"


@pytest.fixture()
def precommit_config() -> dict:
    """Load .pre-commit-config.yaml."""
    with open(_PRECOMMIT) as f:
        return yaml.safe_load(f)


@pytest.fixture()
def all_hooks(precommit_config: dict) -> list[dict]:
    """Extract a flat list of all hook dicts with their repo info."""
    hooks = []
    for repo in precommit_config.get("repos", []):
        for hook in repo.get("hooks", []):
            hooks.append({**hook, "_repo": repo.get("repo", "")})
    return hooks


@pytest.fixture()
def hook_ids(all_hooks: list[dict]) -> list[str]:
    """Extract ordered list of hook IDs."""
    return [h["id"] for h in all_hooks]


# ---------------------------------------------------------------------------
# Scenario: Ruff check runs first (before ruff format)
# ---------------------------------------------------------------------------


class TestPrecommitHookOrder:
    """Hooks MUST run in order: ruff (check) → ruff-format → mypy."""

    def test_ruff_before_ruff_format(self, hook_ids: list[str]) -> None:
        """ruff MUST appear before ruff-format."""
        assert "ruff" in hook_ids, f"ruff hook not found. Hooks: {hook_ids}"
        assert "ruff-format" in hook_ids, f"ruff-format hook not found. Hooks: {hook_ids}"
        ruff_idx = hook_ids.index("ruff")
        format_idx = hook_ids.index("ruff-format")
        assert ruff_idx < format_idx, f"ruff (index {ruff_idx}) must come before ruff-format (index {format_idx})"

    def test_ruff_format_before_mypy(self, hook_ids: list[str]) -> None:
        """ruff-format MUST appear before mypy."""
        assert "mypy" in hook_ids, f"mypy hook not found. Hooks: {hook_ids}"
        format_idx = hook_ids.index("ruff-format")
        mypy_idx = hook_ids.index("mypy")
        assert format_idx < mypy_idx, f"ruff-format (index {format_idx}) must come before mypy (index {mypy_idx})"


# ---------------------------------------------------------------------------
# Scenario: Hooks scope to bot and tests directories
# ---------------------------------------------------------------------------


class TestPrecommitFilesPattern:
    """Ruff and mypy hooks MUST use files: ^(bot/|tests/)."""

    def test_ruff_check_files_pattern(self, all_hooks: list[dict]) -> None:
        """ruff check hook MUST scope to bot/ and tests/."""
        ruff_hook = self._find_hook(all_hooks, "ruff")
        assert ruff_hook is not None, "ruff hook not found"
        files = ruff_hook.get("files", "")
        assert "bot/" in files, f"ruff files missing 'bot/': {files}"
        assert "tests/" in files, f"ruff files missing 'tests/': {files}"

    def test_ruff_format_files_pattern(self, all_hooks: list[dict]) -> None:
        """ruff-format hook MUST scope to bot/ and tests/."""
        format_hook = self._find_hook(all_hooks, "ruff-format")
        assert format_hook is not None, "ruff-format hook not found"
        files = format_hook.get("files", "")
        assert "bot/" in files, f"ruff-format files missing 'bot/': {files}"
        assert "tests/" in files, f"ruff-format files missing 'tests/': {files}"

    def test_mypy_files_pattern(self, all_hooks: list[dict]) -> None:
        """mypy hook MUST scope to bot/ and tests/."""
        mypy_hook = self._find_hook(all_hooks, "mypy")
        assert mypy_hook is not None, "mypy hook not found"
        files = mypy_hook.get("files", "")
        assert "bot/" in files, f"mypy files missing 'bot/': {files}"
        assert "tests/" in files, f"mypy files missing 'tests/': {files}"

    def test_ruff_check_not_hardcoded_allowlist(self, all_hooks: list[dict]) -> None:
        """ruff files MUST NOT be a hardcoded file allowlist (per-file pattern)."""
        ruff_hook = self._find_hook(all_hooks, "ruff")
        assert ruff_hook is not None
        files = ruff_hook.get("files", "")
        # Hardcoded allowlists contain specific .py filenames
        assert ".py" not in files, f"ruff files appears to be a hardcoded allowlist: {files}"

    @staticmethod
    def _find_hook(hooks: list[dict], hook_id: str) -> dict | None:
        for h in hooks:
            if h["id"] == hook_id:
                return h
        return None
