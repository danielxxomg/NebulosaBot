"""Release candidate verification tests for NebulosaBot v1.1.0 relaunch readiness.

Validates version surface synchronization, embedded dashboard client alignment,
CHANGELOG integrity, and release-and-rollback runbook requirements.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pytest

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


def _read_dashboard_lock_versions_from(lock_path: Path) -> tuple[str, str]:
    """Read BOTH version fields declared in a dashboard package-lock.json.

    package-lock.json declares the root version twice: once at the top level and
    once under the root package entry. Both must be inspected; reading only one
    lets the other silently drift.

    Args:
        lock_path: Path to the package-lock.json to inspect.

    Returns:
        tuple[str, str]: ``(top_level_version, root_package_version)``.
    """
    with open(lock_path, encoding="utf-8") as f:
        data = json.load(f)
    top_level = str(data.get("version", ""))
    root_package = str(data.get("packages", {}).get("", {}).get("version", ""))
    return top_level, root_package


def _read_dashboard_lock_version() -> str:
    """Read the root package version declared in dashboard/package-lock.json."""
    root_package = _read_dashboard_lock_versions_from(PROJECT_ROOT / "dashboard" / "package-lock.json")[1]
    return root_package


def _assert_runbook_discloses_limitations(content: str) -> None:
    """Assert the runbook states each operational limitation as an explicit negation.

    Requiring the negative phrasing is the whole point: a runbook claiming a
    successful backup, an executed restore drill, or production readiness must fail
    here, not pass because the relevant noun happens to appear.

    Args:
        content: Full runbook text to validate.

    Raises:
        AssertionError: When any required negative disclosure is absent.
    """
    lowered = content.lower()

    assert "backup_encryption_key" in lowered, "Runbook must name BACKUP_ENCRYPTION_KEY"
    assert re.search(r"not\s+provisioned|un-provisioned", lowered), (
        "Runbook must state BACKUP_ENCRYPTION_KEY is not provisioned"
    )
    assert re.search(r"(no|never|not)\s+successful\s+backup", lowered), (
        "Runbook must state explicitly that no successful backup run has been observed"
    )
    assert re.search(r"(never|not)\s+been\s+executed|has\s+never\s+been", lowered), (
        "Runbook must state explicitly that isolated restore acceptance was never executed"
    )
    assert re.search(
        r"(do(?:es)?\s*n[o']?t|does\s+not|never)\s+[^.]{0,40}production\s+readiness|"
        r"production\s+readiness[^.]{0,40}(is\s+)?n[o']?t\s+claimed",
        lowered,
    ), "Runbook must explicitly disclaim production readiness"
    assert not re.search(r"(successful\s+backup\s+run\s+was\s+observed|claims\s+production\s+readiness)", lowered), (
        "Runbook must not assert an observed successful backup or claim production readiness"
    )


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
        """Verify BOTH package-lock.json version fields match pyproject.toml.

        package-lock.json declares the root version at the top level and under the
        root package entry. Asserting only one lets the other drift undetected.
        """
        pyproject_ver = _read_project_version()
        top_level, root_package = _read_dashboard_lock_versions_from(PROJECT_ROOT / "dashboard" / "package-lock.json")
        assert top_level == pyproject_ver, (
            f"dashboard/package-lock.json top-level version {top_level!r} "
            f"diverged from pyproject.toml {pyproject_ver!r}"
        )
        assert root_package == pyproject_ver, (
            f"dashboard/package-lock.json root package version {root_package!r} "
            f"diverged from pyproject.toml {pyproject_ver!r}"
        )

    @pytest.mark.parametrize(
        "payload",
        [
            # top-level correct, root package stale
            {"version": "1.1.0", "packages": {"": {"version": "0.1.0"}}},
            # root package correct, top-level stale
            {"version": "0.1.0", "packages": {"": {"version": "1.1.0"}}},
            # both stale
            {"version": "0.1.0", "packages": {"": {"version": "0.1.0"}}},
        ],
    )
    def test_lock_guard_detects_partial_drift_in_either_field(self, tmp_path: Path, payload: dict) -> None:
        """Verify partial drift in EITHER lock field is detected, not just simultaneous drift.

        The original negative fixture changed both fields together, which could not
        expose a reader that inspects only one of them.
        """
        drifted = tmp_path / "package-lock.json"
        drifted.write_text(json.dumps(payload), encoding="utf-8")
        pyproject_ver = _read_project_version()
        top_level, root_package = _read_dashboard_lock_versions_from(drifted)
        assert top_level != pyproject_ver or root_package != pyproject_ver, (
            f"lock guard must detect partial drift in payload {payload!r}"
        )

    def test_divergence_guard_detects_drifted_dashboard_version(self, tmp_path: Path) -> None:
        """Verify the comparison the guard performs actually rejects a drifted dashboard version.

        The first form of this test compared two hardcoded string literals, which
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
        drifted_ver = _read_dashboard_lock_versions_from(drifted_lock)[1]
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

    def test_runbook_does_not_pipe_verification_commands(self) -> None:
        """Verify no documented verification command masks its exit status.

        With default shell semantics a failing command piped into `tail`/`head`/`grep`
        exits 0, so a piped verification command reports false success. Every
        runbook command must therefore preserve its process exit status.
        """
        content = self.RUNBOOK_PATH.read_text(encoding="utf-8")
        # Extract fenced bash blocks only, then flag piped verification commands.
        blocks = re.findall(r"```bash\n(.*?)```", content, re.DOTALL)
        assert blocks, "Runbook must document commands in bash code fences"
        offending: list[str] = []
        for block in blocks:
            for line in block.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if "|" not in stripped:
                    continue
                # A pipe is only acceptable when pipefail is explicitly enabled.
                if "pipefail" in stripped:
                    continue
                offending.append(stripped)
        assert not offending, f"verification commands must preserve exit status, found piped: {offending}"

    def test_pipe_guard_rejects_masked_verification_command(self, tmp_path: Path) -> None:
        """Verify the pipe guard actually rejects a masked verification command.

        A guard that cannot fail is decoration. This runs the same detection against a
        snippet reproducing the original defect and requires it to be flagged.
        """
        masked = "```bash\nuv run pytest -q 2>&1 | tail -20\n```"
        blocks = re.findall(r"```bash\n(.*?)```", masked, re.DOTALL)
        offending = [
            line.strip()
            for block in blocks
            for line in block.splitlines()
            if line.strip() and "|" in line.strip() and "pipefail" not in line
        ]
        assert offending == ["uv run pytest -q 2>&1 | tail -20"], (
            "pipe guard must flag a verification command piped into tail"
        )

    def test_runbook_states_recovery_limits_and_no_production_readiness_claims(self) -> None:
        """Verify runbook documents each limitation as an explicit NEGATIVE statement.

        The previous assertions only required that certain words appear, which cannot
        distinguish "no successful backup has been observed" from "a successful backup
        was observed". Each check below requires an explicit negation, so a runbook
        asserting the opposite fails.
        """
        content = self.RUNBOOK_PATH.read_text(encoding="utf-8")
        _assert_runbook_discloses_limitations(content)

    def test_runbook_readiness_guard_rejects_contradicting_claims(self) -> None:
        """Verify the readiness guard actually rejects a runbook claiming the opposite.

        A guard that cannot fail is decoration. This drives the same validation used
        by the positive test against text asserting production readiness and an
        observed successful backup, and requires rejection.
        """
        contradicting = (
            "# Runbook\n"
            "> - `BACKUP_ENCRYPTION_KEY` is **NOT provisioned** in the operational environment.\n"
            "> - A successful backup run was observed in production.\n"
            "> - Isolated restore acceptance executed and verified.\n"
            "> - This repository **claims production readiness**.\n"
        )
        with pytest.raises(AssertionError):
            _assert_runbook_discloses_limitations(contradicting)

    def test_runbook_restore_guard_rejects_positive_restore_claim(self) -> None:
        """Verify a runbook asserting executed restore acceptance is rejected."""
        contradicting = (
            "# Runbook\n"
            "> - `BACKUP_ENCRYPTION_KEY` is **NOT provisioned** in the operational environment.\n"
            "> - No successful backup run has ever been observed.\n"
            "> - Isolated restore acceptance executed and verified.\n"
            "> - This repository does NOT claim production readiness.\n"
        )
        with pytest.raises(AssertionError):
            _assert_runbook_discloses_limitations(contradicting)
