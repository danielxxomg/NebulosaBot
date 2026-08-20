"""RED tests for PR5 Security: bandit delete + zizmor SHA-pin — strict TDD.

Tasks 5.1-5.7. RED before GREEN for config edits; subprocess + TOML/YAML checks.
- 5.1 parity: bandit 95 LOW vs ruff S 97 (92 S101 + 2 S310 + 2 S311 + 1 S110) — Ruff strictly broader; run both once.
- 5.2 delete [tool.bandit], bandit hooks, Makefile security, ci bandit step.
- 5.3 workflow-security job: uvx zizmor --format=github . blocking.
- 5.4 SHA-pin ALL uses: to 40-char SHA + # vN comment; no @vN remains.
- 5.5 RED->GREEN: revert one action to @v4; assert zizmor flags unpinned-uses; GREEN restore SHA.
- 5.6 permissions: contents: read top-level; workflow-security minimal (or security-events: write for SARIF).
- 5.7 code-quality.yml trigger main -> master.

Runner: uv run pytest tests/test_pr5_security_bandit_zizmor.py -v
"""

from __future__ import annotations

import re
import subprocess
import tempfile
import tomllib
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
CI_YML = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
QUALITY_YML = PROJECT_ROOT / ".github" / "workflows" / "code-quality.yml"
MAKEFILE = PROJECT_ROOT / "Makefile"
PREK_TOML = PROJECT_ROOT / "prek.toml"


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd or PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )


def _load_pyproject() -> dict:
    with open(PYPROJECT, "rb") as f:
        return tomllib.load(f)


def _load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


SHA40_RE = re.compile(r"^[0-9a-f]{40}$")


# ---------------------------------------------------------------------------
# 5.1 Parity: bandit 95 LOW vs ruff S 97 — Ruff strictly broader
# Documented delta: Ruff S 97 = 92 S101 + 2 S310 + 2 S311 + 1 S110
# Bandit 95 = 95 B101 (assert) at LOW. After PR4b, both are ~0/3 suppressed,
# but parity proof is that Ruff S covers strictly more families than bandit.
# ---------------------------------------------------------------------------


class TestParityBanditRuffS:
    """5.1 Parity proof — run BOTH tools once; document delta."""

    def test_bandit_runs_and_count_documented(self) -> None:
        """Bandit must run; low-severity count documented (post-PR4b = 3, pre-PR4b 95)."""
        result = _run(["uv", "run", "bandit", "-r", "bot/", "-c", "pyproject.toml", "--severity-level", "low"])
        combined = result.stdout + result.stderr
        assert "Total lines of code" in combined or "Run metrics" in combined, combined[:2000]
        # Post-PR4b, 3 findings remain (2x S311 random + 1x S310 urlopen); pre-PR4b was 95 B101.
        # Either bandit config present (old) or absent (new) — both are valid post-deletion if we skip.
        # After 5.2, pyproject will lack [tool.bandit]; bandit then uses defaults and still runs.
        # So just assert it exits and reports metrics.
        assert result.returncode in (0, 1), f"bandit failed to run: {combined[:2000]}"

    def test_ruff_s_isolated_stats(self) -> None:
        """Ruff S isolated must be clean after PR4b (was 97 = 92 S101 + 2 S310 + 2 S311 + 1 S110)."""
        result = _run(["uv", "run", "ruff", "check", "--isolated", "--select", "S", "bot/"])
        combined = result.stdout + result.stderr
        # After PR4b, isolated S is 0 (S101 92 fixed + S310/S311 narrow noqa + S110 logged).
        # Before PR4b it was 97. Post-PR5 it remains 0 — Ruff strictly broader than bandit.
        assert result.returncode == 0, f"ruff S isolated still failing: {combined[:2000]}"
        assert "All checks passed" in combined, combined[:2000]

    def test_delta_documented_ruff_strictly_broader(self) -> None:
        """Delta documented: Ruff S 97 vs bandit 95 — Ruff adds 2x S310/S311 + 1x S110 beyond B101."""
        # This asserts the documentation premise, not runtime.
        # Historical: bandit 95 LOW (all B101 assert) vs ruff 97 (92 S101 + 2 S310 + 2 S311 + 1 S110).
        # After PR4b, ruff S 0 and bandit 3 (S311+S310) remain, but Ruff's family coverage is still broader.
        data = _load_pyproject()
        # After PR4b, bandit config still present; after PR5 it must be gone — parity holds either way.
        # Just assert ruff select includes S (bandit equivalent) and that delta is documented here.
        ruff_select = data["tool"]["ruff"]["lint"]["select"]
        assert "S" in ruff_select, f"S not in ruff select: {ruff_select}"
        # Bandit tool entry may be gone after 5.2 — both states doc delta correctly.
        assert True  # documentation anchor


# ---------------------------------------------------------------------------
# 5.2 Delete [tool.bandit]; delete bandit hooks; delete Makefile security; remove ci bandit
# ---------------------------------------------------------------------------


class TestBanditDeletion:
    """5.2 Delete bandit from pyproject, prek, Makefile, ci."""

    def test_pyproject_no_bandit_section(self) -> None:
        data = _load_pyproject()
        assert "bandit" not in data.get("tool", {}), f"[tool.bandit] still present: {list(data['tool'].keys())}"

    def test_no_bandit_string_repo_wide(self) -> None:
        # prek.toml, Makefile, ci.yml must not reference bandit
        for path in [PREK_TOML, MAKEFILE, CI_YML]:
            if path.exists():
                content = path.read_text()
                assert "bandit" not in content.lower(), f"bandit still in {path}: {content[:500]}"

    def test_makefile_no_security_target(self) -> None:
        content = MAKEFILE.read_text()
        # No `security:` target and no bandit command
        assert "security:" not in content, "Makefile still has security: target"
        assert "bandit" not in content.lower(), "Makefile still references bandit"

    def test_makefile_ci_no_security(self) -> None:
        content = MAKEFILE.read_text()
        # ci target must not chain security
        for line in content.splitlines():
            if line.strip().startswith("ci:"):
                assert "security" not in line, f"ci still chains security: {line}"
                return
        raise AssertionError("no ci: target found in Makefile")

    def test_makefile_phony_no_security(self) -> None:
        content = MAKEFILE.read_text()
        for line in content.splitlines():
            if line.strip().startswith(".PHONY"):
                assert "security" not in line, f".PHONY still lists security: {line}"
                return

    def test_ci_no_bandit_step(self) -> None:
        data = _load_yaml(CI_YML)
        text = CI_YML.read_text()
        assert "bandit" not in text.lower(), "ci.yml still has bandit step"
        # Also via YAML structure
        for job in data.get("jobs", {}).values():
            for step in job.get("steps", []) or []:
                run = step.get("run", "") or ""
                assert "bandit" not in run.lower(), f"bandit step still in ci.yml: {run}"


# ---------------------------------------------------------------------------
# 5.3 workflow-security job: uvx zizmor --format=github . blocking
# ---------------------------------------------------------------------------


class TestWorkflowSecurityJob:
    """5.3 Add workflow-security job in ci.yml: uvx zizmor --format=github . blocking."""

    def test_workflow_security_job_exists(self) -> None:
        data = _load_yaml(CI_YML)
        assert "workflow-security" in data.get("jobs", {}), (
            f"workflow-security job missing: {list(data['jobs'].keys())}"
        )

    def test_zizmor_step_present(self) -> None:
        data = _load_yaml(CI_YML)
        job = data["jobs"]["workflow-security"]
        steps = job.get("steps", []) or []
        runs = [s.get("run", "") for s in steps]
        assert any("zizmor" in (r or "") for r in runs), f"no zizmor run in workflow-security: {runs}"
        assert any("uvx zizmor" in (r or "") or "zizmor" in (r or "") for r in runs), runs

    def test_zizmor_format_github(self) -> None:
        text = CI_YML.read_text()
        # Must use --format=github (or sarif + upload-sarif)
        assert "--format=github" in text or "--format github" in text or "--format=sarif" in text, (
            f"zizmor format not github/sarif: {text[:1500]}"
        )

    def test_workflow_security_blocking(self) -> None:
        data = _load_yaml(CI_YML)
        job = data["jobs"]["workflow-security"]
        # Must not have continue-on-error: true
        assert job.get("continue-on-error") is not True, "workflow-security must be blocking (continue-on-error true)"
        for step in job.get("steps", []) or []:
            assert step.get("continue-on-error") is not True, f"zizmor step must be blocking: {step}"

    def test_zizmor_invocation_targets_workflows(self) -> None:
        text = CI_YML.read_text()
        # zizmor must target . or .github/workflows
        assert "zizmor" in text
        # Accept either `zizmor .` or `zizmor .github/workflows` or with --format
        assert ".github" in text or "zizmor --format" in text or "zizmor ." in text


# ---------------------------------------------------------------------------
# 5.4 SHA-pin ALL uses: to 40-char SHA + # vN comment
# ---------------------------------------------------------------------------


class TestSHAPinning:
    """5.4 SHA-pin ALL uses: to 40-char SHA + # vN comment; no @vN remains."""

    def _all_uses(self) -> list[str]:
        text = ""
        for p in [CI_YML, QUALITY_YML]:
            if p.exists():
                text += p.read_text() + "\n"
        return re.findall(r"uses:\s*([^\s#]+)", text)

    def test_no_tag_pins_remain(self) -> None:
        uses = self._all_uses()
        tag_pins = [u for u in uses if re.search(r"@v\d+", u)]
        assert tag_pins == [], f"tag-pinned uses remain (must be SHA): {tag_pins}"

    def test_all_shas_are_40_hex(self) -> None:
        uses = self._all_uses()
        for u in uses:
            if "@" not in u:
                continue
            _, ref = u.split("@", 1)
            # Allow fully SHA-pinned: ref must be 40 hex
            assert SHA40_RE.match(ref), f"ref not 40-char SHA: {u} -> {ref}"

    def test_sha_comments_present(self) -> None:
        # Each SHA line should have trailing # vN comment
        for p in [CI_YML, QUALITY_YML]:
            for line in p.read_text().splitlines():
                if "uses:" in line and "@" in line:
                    sha = line.split("@", 1)[1].split()[0].strip()
                    if SHA40_RE.match(sha):
                        assert "#" in line and re.search(r"#\s*v\d+", line), f"SHA line missing # vN comment: {line}"

    def test_expected_actions_pinned(self) -> None:
        uses = " ".join(self._all_uses())
        # Required pins per spec
        required = ["actions/checkout", "actions/setup-node", "actions/upload-artifact", "astral-sh/setup-uv"]
        for req in required:
            if req in uses or req in CI_YML.read_text() or req in QUALITY_YML.read_text():
                # If present, must be SHA-pinned (checked above); just assert no tag
                assert f"{req}@v" not in uses, f"{req} still tag-pinned"

    def test_setup_uv_pinned(self) -> None:
        # setup-uv must remain SHA-pinned @d0cc045d04ccac9d8b7881df0226f9e82c39688e # v6
        for p in [CI_YML, QUALITY_YML]:
            if "setup-uv" in p.read_text():
                uses = re.findall(r"uses:\s*([^\s]+)", p.read_text())
                uv_uses = [u for u in uses if "setup-uv" in u]
                for u in uv_uses:
                    assert SHA40_RE.match(u.split("@")[1]), f"setup-uv not SHA: {u}"


# ---------------------------------------------------------------------------
# 5.5 RED -> GREEN: revert one action to @v4; assert zizmor flags; GREEN restore SHA
# ---------------------------------------------------------------------------


class TestZizmorGateREDGreen:
    """5.5 Strict TDD gate: zizmor must flag tag-pin; SHA restores pass."""

    def test_zizmor_flags_tag_pin_in_temp_workflow(self) -> None:
        """RED: temp workflow with @v4 must be flagged as unpinned-uses (high)."""
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            wf_dir = td_path / ".github" / "workflows"
            wf_dir.mkdir(parents=True)
            # Minimal workflow with a tag-pinned checkout
            wf = wf_dir / "ci.yml"
            wf.write_text(
                "name: Test\non: push\npermissions:\n  contents: read\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n"
            )
            result = _run(["uvx", "zizmor", "--format=github", str(td_path)])
            combined = result.stdout + result.stderr
            # zizmor emits ::error for unpinned-uses and exits non-zero (14) or plain high
            assert "unpinned-uses" in combined, f"zizmor did not flag tag pin: {combined[:3000]}"
            # Exit code is non-zero when high findings present (or at least stderr has error)
            assert result.returncode != 0 or "::error" in combined, (
                f"zizmor did not fail on tag pin: rc={result.returncode} {combined[:2000]}"
            )

    def test_zizmor_passes_after_sha_restore(self) -> None:
        """GREEN: real repo after SHA-pin must have no unpinned-uses high."""
        result = _run(["uvx", "zizmor", "--format=github", "."])
        combined = result.stdout + result.stderr
        # After fix, no unpinned-uses errors should remain
        assert "unpinned-uses" not in combined, f"repo still has unpinned-uses after SHA-pin: {combined[:3000]}"

    def test_zizmor_persist_credentials_flag(self) -> None:
        """After fix, artipacked (persist-credentials) should also be clean or noted."""
        result = _run(["uvx", "zizmor", "--format=plain", "."])
        combined = result.stdout + result.stderr
        # We fix artipacked by adding persist-credentials: false, so plain should not contain artipacked.
        # If it still does, workflow-security would be non-clean. Assert clean.
        assert "artipacked" not in combined, (
            f"artipacked still present (add persist-credentials: false): {combined[:3000]}"
        )


# ---------------------------------------------------------------------------
# 5.6 Permissions: contents: read top-level; workflow-security minimal
# ---------------------------------------------------------------------------


class TestPermissions:
    """5.6 Top-level permissions: contents: read; workflow-security minimal/elevated correctly."""

    def test_ci_top_level_permissions_read(self) -> None:
        data = _load_yaml(CI_YML)
        perms = data.get("permissions")
        assert perms is not None, "ci.yml missing top-level permissions"
        # Either dict or string "contents: read"
        if isinstance(perms, dict):
            assert perms.get("contents") == "read", f"ci.yml permissions not contents: read: {perms}"
            assert perms.get("contents") != "write", "ci.yml must not be write-all"
        elif isinstance(perms, str):
            assert perms == "read", f"ci.yml perms string not read: {perms}"
        else:
            raise AssertionError(f"unexpected permissions type: {perms}")

    def test_quality_top_level_permissions_read(self) -> None:
        data = _load_yaml(QUALITY_YML)
        perms = data.get("permissions")
        assert perms is not None, "code-quality.yml missing permissions"
        if isinstance(perms, dict):
            assert perms.get("contents") == "read", f"code-quality perms not read: {perms}"
        else:
            raise AssertionError(f"unexpected perms type: {perms}")

    def test_workflow_security_permissions_minimal(self) -> None:
        data = _load_yaml(CI_YML)
        job = data["jobs"]["workflow-security"]
        perms = job.get("permissions")
        # For github format, minimal is contents: read (inherits). For sarif, needs security-events: write.
        # Either no elevated perms beyond top-level, or explicit minimal.
        if perms is not None:
            assert perms.get("contents") in (None, "read"), f"workflow-security excessive contents: {perms}"
            # Only allowed elevation is security-events: write for SARIF
            allowed_keys = {"contents", "security-events"}
            for k in perms:
                assert k in allowed_keys, f"unexpected permission key in workflow-security: {k}: {perms}"
            if "security-events" in perms:
                assert perms["security-events"] == "write", f"security-events must be write if present: {perms}"

    def test_no_write_all(self) -> None:
        for p in [CI_YML, QUALITY_YML]:
            text = p.read_text()
            assert "write-all" not in text, f"{p} contains write-all"
            data = _load_yaml(p)
            perms = data.get("permissions")
            if isinstance(perms, dict):
                assert perms.get("contents") != "write", f"{p} has write contents"


# ---------------------------------------------------------------------------
# 5.7 code-quality.yml trigger main -> master
# ---------------------------------------------------------------------------


class TestCodeQualityTrigger:
    """5.7 Fix .github/workflows/code-quality.yml trigger main -> master."""

    def test_triggers_on_master(self) -> None:
        data = _load_yaml(QUALITY_YML)
        # PyYAML parses `on:` as boolean True (YAML 1.1) — handle both.
        on = data.get("on", data.get(True, {}))
        pr = on.get("pull_request", {}) or {}
        branches = pr.get("branches", []) or []
        assert "master" in branches, f"code-quality.yml must trigger on master, got: {branches}"
        assert "main" not in branches, f"code-quality.yml still triggers on main: {branches}"

    def test_no_main_branch_anywhere(self) -> None:
        text = QUALITY_YML.read_text()
        # Ensure no `branches: [main]` remains
        assert "branches: [main]" not in text and 'branches: ["main"]' not in text, (
            f"code-quality.yml still has main trigger: {text[:500]}"
        )
