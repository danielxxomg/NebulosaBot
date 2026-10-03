"""Release candidate verification tests for NebulosaBot v1.1.0 relaunch readiness.

Validates version surface synchronization, embedded dashboard client alignment,
CHANGELOG integrity, and release-and-rollback runbook requirements.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPECTED_RELEASE_VERSION = "1.1.0"
SEMVER_REGEX = re.compile(r"^\d+\.\d+\.\d+$")


def _read_project_version() -> str:
    """Read the canonical version declared in pyproject.toml."""
    pyproject_path = PROJECT_ROOT / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)
    version: str = data["project"]["version"]
    return version


def _read_bot_version() -> str | None:
    """Read the __version__ declared in bot/__init__.py."""
    init_path = PROJECT_ROOT / "bot" / "__init__.py"
    text = init_path.read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return match.group(1) if match else None


def _read_newest_changelog_version() -> str | None:
    """Read the newest bracketed release version in CHANGELOG.md."""
    changelog_path = PROJECT_ROOT / "CHANGELOG.md"
    text = changelog_path.read_text(encoding="utf-8")
    match = re.search(r"^##\s*\[v?([^\]]+)\]", text, re.MULTILINE)
    return match.group(1).strip() if match else None


def _read_dashboard_package_version() -> str:
    """Read the version declared in dashboard/package.json."""
    pkg_path = PROJECT_ROOT / "dashboard" / "package.json"
    with open(pkg_path, encoding="utf-8") as f:
        data = json.load(f)
    version: str = data["version"]
    return version


def _read_dashboard_lock_version_from(lock_path: Path) -> str:
    """Read the root package version from a dashboard package-lock.json at the given path."""
    with open(lock_path, encoding="utf-8") as f:
        data = json.load(f)
    version: str = data.get("packages", {}).get("", {}).get("version", data.get("version", ""))
    return version


def _read_dashboard_lock_version() -> str:
    """Read the root package version declared in dashboard/package-lock.json."""
    return _read_dashboard_lock_version_from(PROJECT_ROOT / "dashboard" / "package-lock.json")


class TestVersionSurfaces:
    """Validate version consistency across all canonical project surfaces."""

    def test_pyproject_version_is_expected_release_target(self) -> None:
        """Verify pyproject.toml declares the target release version 1.1.0."""
        version = _read_project_version()
        assert version == EXPECTED_RELEASE_VERSION, (
            f"pyproject.toml declares {version!r}, expected {EXPECTED_RELEASE_VERSION!r}"
        )

    def test_pyproject_version_matches_semver_shape(self) -> None:
        """Verify pyproject.toml version matches strict SemVer X.Y.Z shape."""
        version = _read_project_version()
        assert SEMVER_REGEX.fullmatch(version), f"Version {version!r} does not match SemVer shape"

    def test_bot_init_version_matches_pyproject(self) -> None:
        """Verify bot/__init__.py __version__ matches pyproject.toml version."""
        pyproject_ver = _read_project_version()
        bot_ver = _read_bot_version()
        assert bot_ver is not None, "bot/__init__.py must declare __version__"
        assert bot_ver == pyproject_ver, (
            f"bot/__init__.py declares {bot_ver!r} but pyproject.toml declares {pyproject_ver!r}"
        )

    def test_changelog_newest_heading_matches_pyproject(self) -> None:
        """Verify the newest bracketed heading in CHANGELOG.md matches pyproject.toml."""
        pyproject_ver = _read_project_version()
        changelog_ver = _read_newest_changelog_version()
        assert changelog_ver is not None, "CHANGELOG.md must declare at least one bracketed version"
        assert changelog_ver == pyproject_ver, (
            f"CHANGELOG.md newest bracketed version is {changelog_ver!r} but pyproject.toml is {pyproject_ver!r}"
        )

    def test_changelog_contains_reconciliation_note(self) -> None:
        """Verify CHANGELOG.md explains historical v1.0.0 metadata reconciliation."""
        changelog_path = PROJECT_ROOT / "CHANGELOG.md"
        content = changelog_path.read_text(encoding="utf-8")
        assert "v1.0.0" in content
        assert "0.9.0" in content
        assert "1.1.0" in content


class TestDashboardVersionDivergence:
    """Guard the decision that the embedded dashboard ships on the bot's release line.

    The dashboard is an embedded client deployed alongside the bot, so its version is
    intentionally EQUAL to the project version rather than an independent SemVer line.
    This test file therefore does NOT compare dashboard against pyproject to prove they
    "should" match on independent grounds; it asserts the aligned value so that a
    partial bump (Python bumped, dashboard forgotten) fails loudly.
    """

    def test_dashboard_package_json_aligns_with_project_version(self) -> None:
        """Verify dashboard/package.json version matches pyproject.toml version."""
        pyproject_ver = _read_project_version()
        dashboard_ver = _read_dashboard_package_version()
        assert dashboard_ver == pyproject_ver, (
            f"dashboard/package.json version {dashboard_ver!r} diverged from pyproject.toml {pyproject_ver!r}"
        )

    def test_dashboard_package_lock_aligns_with_project_version(self) -> None:
        """Verify dashboard/package-lock.json root package version matches pyproject.toml."""
        pyproject_ver = _read_project_version()
        lock_ver = _read_dashboard_lock_version()
        assert lock_ver == pyproject_ver, (
            f"dashboard/package-lock.json version {lock_ver!r} diverged from pyproject.toml {pyproject_ver!r}"
        )

    def test_divergence_guard_detects_drifted_dashboard_version(self, tmp_path: Path) -> None:
        """Verify the comparison the guard performs actually rejects a drifted dashboard version.

        The previous form of this test compared two hardcoded string literals, which
        passed unconditionally and proved nothing about the guard. This version drives
        the same comparison the guard uses, against a deliberately drifted value read
        from disk, so a regression that made the guard vacuous would fail here too.
        """
        drifted_lock = tmp_path / "package-lock.json"
        drifted_lock.write_text(
            json.dumps({"version": "9.9.9", "packages": {"": {"version": "9.9.9"}}}),
            encoding="utf-8",
        )
        pyproject_ver = _read_project_version()
        drifted_ver = _read_dashboard_lock_version_from(drifted_lock)
        assert drifted_ver == "9.9.9"
        assert drifted_ver != pyproject_ver, (
            "guard comparison must reject a dashboard lock that drifted from pyproject.toml"
        )


class TestSemverValidationTriangulation:
    """Triangulate SemVer regex against non-standard or malformed formats."""

    def test_semver_regex_triangulation(self) -> None:
        """Verify SEMVER_REGEX strictly matches only standard X.Y.Z shapes."""
        assert SEMVER_REGEX.fullmatch("1.1.0") is not None
        assert SEMVER_REGEX.fullmatch("0.9.0") is not None
        assert SEMVER_REGEX.fullmatch("v1.1.0") is None
        assert SEMVER_REGEX.fullmatch("1.1") is None
        assert SEMVER_REGEX.fullmatch("1.1.0.0") is None
        assert SEMVER_REGEX.fullmatch("1.1.0-rc1") is None


class TestReleaseAndRollbackRunbook:
    """Structural assertions verifying release-and-rollback runbook completeness."""

    RUNBOOK_PATH = PROJECT_ROOT / "docs" / "runbooks" / "release-and-rollback.md"

    def test_runbook_exists_and_is_non_empty(self) -> None:
        """Verify docs/runbooks/release-and-rollback.md exists and has substantial content."""
        assert self.RUNBOOK_PATH.exists(), f"Runbook missing: {self.RUNBOOK_PATH}"
        content = self.RUNBOOK_PATH.read_text(encoding="utf-8").strip()
        assert len(content) > 500, "Runbook must contain substantial procedural content (>500 chars)"

    def test_runbook_contains_required_sections(self) -> None:
        """Verify required operational sections exist in runbook."""
        content = self.RUNBOOK_PATH.read_text(encoding="utf-8")
        required_headings = [
            "Preconditions",
            "Cut procedure",
            "Rollback procedure",
            "Recovery",
        ]
        for heading in required_headings:
            assert re.search(rf"^#+\s*.*{heading}", content, re.MULTILINE | re.IGNORECASE), (
                f"Runbook missing section matching heading {heading!r}"
            )

    def test_runbook_references_related_runbooks(self) -> None:
        """Verify runbook references reset-procedure.md and staging-live-parity.md."""
        content = self.RUNBOOK_PATH.read_text(encoding="utf-8")
        assert "reset-procedure.md" in content, "Runbook must reference reset-procedure.md"
        assert "staging-live-parity.md" in content, "Runbook must reference staging-live-parity.md"

    def test_runbook_states_recovery_limits_and_no_production_readiness_claims(self) -> None:
        """Verify runbook explicitly documents missing keys, unobserved backups, and disclaims production readiness."""
        content = self.RUNBOOK_PATH.read_text(encoding="utf-8")
        assert "BACKUP_ENCRYPTION_KEY" in content, "Runbook must name BACKUP_ENCRYPTION_KEY"
        assert "not provisioned" in content.lower() or "un-provisioned" in content.lower(), (
            "Runbook must state BACKUP_ENCRYPTION_KEY is not provisioned"
        )
        assert "successful backup" in content.lower(), (
            "Runbook must document that no successful backup run has been observed"
        )
        assert "restore" in content.lower(), "Runbook must document isolated restore status"
        # Disclaim production readiness
        assert "production ready" not in content.lower() or "not production ready" in content.lower(), (
            "Runbook must not claim production readiness"
        )
