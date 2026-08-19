"""RED tests for PR1 uv foundation — PEP735 groups + lock + setup-uv + uv audit.

Strict TDD: these tests FAIL on the pre-migration baseline and PASS after PR1 lands.
Work unit: PR1 uv foundation (tasks 1.1-1.7). Runner: uv run pytest.
"""

from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
UV_LOCK = PROJECT_ROOT / "uv.lock"
CI_YML = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
MAKEFILE = PROJECT_ROOT / "Makefile"


def _load_pyproject() -> dict:
    with open(PYPROJECT, "rb") as f:
        return tomllib.load(f)


def _read_ci() -> str:
    return CI_YML.read_text(encoding="utf-8")


def _read_makefile() -> str:
    return MAKEFILE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1.1 uv lock --check exits 0 (stale lock breaks downstream PRs)
# ---------------------------------------------------------------------------


class TestUvLockCheck:
    def test_uv_lock_check_exits_zero(self) -> None:
        """uv lock --check MUST exit 0 — lock matches pyproject after migration."""
        result = subprocess.run(
            ["uv", "lock", "--check"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"uv lock --check failed (exit {result.returncode}). "
            f"stdout: {result.stdout[:500]} stderr: {result.stderr[:500]}"
        )

    def test_uv_sync_locked_exits_zero(self) -> None:
        """uv sync --locked MUST exit 0 — groups migration keeps dev resolvable."""
        result = subprocess.run(
            ["uv", "sync", "--locked", "--dry-run"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
        )
        # --dry-run still validates lock; exit 0 means lock fresh
        assert result.returncode == 0, (
            f"uv sync --locked --dry-run failed (exit {result.returncode}). stderr: {result.stderr[:800]}"
        )


# ---------------------------------------------------------------------------
# 1.2 dependency-groups dev migration + ty exact pin
# ---------------------------------------------------------------------------


class TestDependencyGroups:
    def test_dependency_groups_dev_exists(self) -> None:
        """[dependency-groups] dev MUST exist (PEP735, replaces extras)."""
        data = _load_pyproject()
        assert "dependency-groups" in data, "missing [dependency-groups] table"
        assert "dev" in data["dependency-groups"], "missing [dependency-groups].dev"

    def test_dependency_groups_dev_contains_ty_exact(self) -> None:
        """dev group MUST contain ty==0.0.18 exact pin."""
        data = _load_pyproject()
        dev = data.get("dependency-groups", {}).get("dev", [])
        joined = " ".join(str(x) for x in dev)
        assert "ty==0.0.18" in joined, f"ty==0.0.18 not in dev group: {dev}"

    def test_dependency_groups_dev_contains_ruff_pinned(self) -> None:
        """dev group MUST retain ruff==0.15.20."""
        data = _load_pyproject()
        dev = data.get("dependency-groups", {}).get("dev", [])
        joined = " ".join(str(x) for x in dev)
        assert "ruff==0.15.20" in joined, f"ruff==0.15.20 not in dev group: {dev}"

    def test_dependency_groups_dev_contains_pytest_stack(self) -> None:
        """dev group MUST contain pytest + plugins + hypothesis + freezegun."""
        data = _load_pyproject()
        dev = data.get("dependency-groups", {}).get("dev", [])
        joined = " ".join(str(x) for x in dev).lower()
        for needle in ["pytest", "pytest-asyncio", "pytest-cov", "pytest-randomly", "hypothesis", "freezegun"]:
            assert needle.lower() in joined, f"{needle} not in dev group: {dev}"

    def test_optional_dependencies_dev_removed(self) -> None:
        """[project.optional-dependencies] dev MUST be absent after migration."""
        data = _load_pyproject()
        opt = data.get("project", {}).get("optional-dependencies")
        if opt is not None:
            assert "dev" not in opt, f"[project.optional-dependencies].dev still present: {list(opt.keys())}"

    def test_no_mypy_in_dependency_groups(self) -> None:
        """mypy MUST NOT be in [dependency-groups] dev (ty replaces)."""
        data = _load_pyproject()
        dev = data.get("dependency-groups", {}).get("dev", [])
        joined = " ".join(str(x) for x in dev).lower()
        assert "mypy" not in joined, f"mypy still in dev group: {dev}"

    def test_no_bandit_in_dependency_groups(self) -> None:
        """bandit MUST NOT be in [dependency-groups] dev (S replaces)."""
        data = _load_pyproject()
        dev = data.get("dependency-groups", {}).get("dev", [])
        joined = " ".join(str(x) for x in dev).lower()
        assert "bandit" not in joined, f"bandit still in dev group: {dev}"

    def test_no_pip_audit_in_dependency_groups(self) -> None:
        """pip-audit MUST NOT be in dev group (uv audit replaces)."""
        data = _load_pyproject()
        dev = data.get("dependency-groups", {}).get("dev", [])
        joined = " ".join(str(x) for x in dev).lower()
        assert "pip-audit" not in joined, f"pip-audit still in dev group: {dev}"


# ---------------------------------------------------------------------------
# 1.3 [tool.uv] default-groups = ["dev"] + runtime deps preserved
# ---------------------------------------------------------------------------


class TestToolUv:
    def test_tool_uv_default_groups_dev(self) -> None:
        """[tool.uv] default-groups MUST be [\"dev\"]."""
        data = _load_pyproject()
        uv_cfg = data.get("tool", {}).get("uv", {})
        assert uv_cfg.get("default-groups") == ["dev"], f"got {uv_cfg.get('default-groups')}"

    def test_runtime_deps_preserved(self) -> None:
        """[project] dependencies MUST retain runtime deps (Pterodactyl safe)."""
        data = _load_pyproject()
        deps = data.get("project", {}).get("dependencies", [])
        joined = " ".join(str(x) for x in deps).lower()
        for needle in ["discord.py", "supabase", "python-dotenv", "pillow", "pyjwt", "psycopg"]:
            assert needle.lower() in joined, f"runtime dep {needle} missing from [project].dependencies: {deps}"

    def test_requirements_txt_still_pinned(self) -> None:
        """requirements.txt MUST remain present and pip-resolvable (Pterodactyl)."""
        req = PROJECT_ROOT / "requirements.txt"
        assert req.is_file(), "requirements.txt missing"
        content = req.read_text(encoding="utf-8")
        for needle in ["discord.py", "supabase", "python-dotenv", "Pillow"]:
            assert needle.lower() in content.lower(), f"{needle} missing from requirements.txt"


# ---------------------------------------------------------------------------
# 1.4 uv.lock regenerated — contains ty, lacks mypy/bandit
# ---------------------------------------------------------------------------


class TestUvLockContent:
    def test_lock_contains_ty(self) -> None:
        """uv.lock MUST contain ty 0.0.18."""
        content = UV_LOCK.read_text(encoding="utf-8")
        assert 'name = "ty"' in content, "uv.lock missing ty package"

    def test_lock_lacks_mypy(self) -> None:
        """uv.lock MUST NOT contain mypy (ty replaces)."""
        content = UV_LOCK.read_text(encoding="utf-8")
        assert 'name = "mypy"' not in content, "uv.lock still contains mypy"

    def test_lock_lacks_bandit(self) -> None:
        """uv.lock MUST NOT contain bandit (S replaces)."""
        content = UV_LOCK.read_text(encoding="utf-8")
        assert 'name = "bandit"' not in content, "uv.lock still contains bandit"

    def test_lock_no_pip_audit(self) -> None:
        """uv.lock MUST NOT contain pip-audit (uv audit replaces)."""
        content = UV_LOCK.read_text(encoding="utf-8")
        # pip-audit was never in lock (installed via --with), but assert no stray entry
        assert 'name = "pip-audit"' not in content, "uv.lock contains pip-audit"


# ---------------------------------------------------------------------------
# 1.5 ci.yml: setup-uv SHA-pin, no setup-python/cache, uv sync --locked
# ---------------------------------------------------------------------------


class TestCiSetupUv:
    def test_ci_uses_setup_uv_sha_pinned(self) -> None:
        """ci.yml MUST use astral-sh/setup-uv@<40-char-sha> # v6 (SHA-pin)."""
        content = _read_ci()
        pattern = re.compile(r"astral-sh/setup-uv@[0-9a-f]{40}\s+#\s*v6")
        assert pattern.search(content), (
            "ci.yml missing astral-sh/setup-uv@<40-char-sha> # v6. "
            f"Got setup-uv refs: {[l.strip() for l in content.splitlines() if 'setup-uv' in l]}"
        )

    def test_ci_no_setup_python(self) -> None:
        """ci.yml MUST NOT use actions/setup-python (replaced by setup-uv)."""
        content = _read_ci()
        assert "actions/setup-python" not in content, "ci.yml still references actions/setup-python"

    def test_ci_no_actions_cache_uv(self) -> None:
        """ci.yml MUST NOT use actions/cache for uv (setup-uv handles caching)."""
        content = _read_ci()
        # actions/cache@v4 with path ~/.cache/uv is the replaced pattern
        assert "actions/cache" not in content, "ci.yml still references actions/cache"

    def test_ci_no_pip_install_uv(self) -> None:
        """ci.yml MUST NOT run 'pip install uv' (setup-uv installs uv)."""
        content = _read_ci()
        assert "pip install uv" not in content, "ci.yml still runs pip install uv"

    def test_ci_uses_uv_sync_locked(self) -> None:
        """ci.yml MUST install deps via 'uv sync --locked' (not --extra dev)."""
        content = _read_ci()
        assert "uv sync --locked" in content, "ci.yml missing 'uv sync --locked'"
        assert "uv sync --extra dev" not in content, "ci.yml still uses 'uv sync --extra dev'"


# ---------------------------------------------------------------------------
# 1.6 ci.yml: uv audit replaces pip-audit, pip-audit-weekly deleted
# ---------------------------------------------------------------------------


class TestCiAudit:
    def test_ci_no_pip_audit_references(self) -> None:
        """ci.yml MUST NOT contain any 'pip-audit' string after PR1."""
        content = _read_ci()
        assert "pip-audit" not in content, (
            f"ci.yml still contains pip-audit: {[l for l in content.splitlines() if 'pip-audit' in l]}"
        )

    def test_ci_has_uv_audit(self) -> None:
        """ci.yml quality job MUST run 'uv audit'."""
        content = _read_ci()
        assert "uv audit" in content, "ci.yml missing 'uv audit' step"

    def test_ci_no_pip_audit_weekly_job(self) -> None:
        """ci.yml MUST NOT define pip-audit-weekly job."""
        content = _read_ci()
        assert "pip-audit-weekly" not in content, "ci.yml still defines pip-audit-weekly job"


# ---------------------------------------------------------------------------
# 1.7 Makefile: audit target runs uv audit
# ---------------------------------------------------------------------------


class TestMakefileAudit:
    def test_makefile_audit_runs_uv_audit(self) -> None:
        """Makefile audit target MUST run 'uv audit'."""
        content = _read_makefile()
        # Find audit target block
        assert "uv audit" in content, "Makefile missing 'uv audit' in audit target"
        # Purge legacy pip-audit pattern
        assert "pip-audit" not in content, (
            f"Makefile still contains pip-audit: {[l for l in content.splitlines() if 'pip-audit' in l]}"
        )

    def test_makefile_audit_target_exists(self) -> None:
        """Makefile MUST define an 'audit:' target."""
        content = _read_makefile()
        assert re.search(r"^audit\s*:", content, re.MULTILINE), "Makefile missing 'audit:' target"
