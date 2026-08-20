"""RED tests for PR4b Ruff security: S101/S310/S311/S110 — strict TDD.

Tasks 4b.1-4b.5. These tests capture the RED baseline (97 findings via --isolated)
and assert GREEN after the fix lands (per-file-ignores removal + S101 rewrites +
narrow noqa disposition). Follows PR4a pattern (isolated --statistics + TOML checks).

Runner: uv run pytest tests/test_pr4b_ruff_security.py -v
"""

from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = PROJECT_ROOT / "pyproject.toml"


def _load_pyproject() -> dict:
    with open(PYPROJECT, "rb") as f:
        return tomllib.load(f)


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )


# ---------------------------------------------------------------------------
# 4b.1 RED: isolated S baseline is 92 S101 + 2 S310 + 2 S311 + 1 S110 = 97
# These assert GREEN after fix (isolated 0). Before fix they were RED.
# The pre-fix counts are preserved here and in apply-progress.md evidence.
# ---------------------------------------------------------------------------


class TestRuffSecurityBaseline:
    """4b.1 RED: before PR4b isolated S was 97 (92 S101 + 2 S310 + 2 S311 + 1 S110).

    After GREEN, isolated must be 0 for each code. The 97 count is the
    pre-fix baseline recorded before per-file-ignores removal + rewrites.
    """

    def test_isolated_s101_zero_after_fix(self) -> None:
        """Post-fix: isolated S101 must be 0 (RED was 92)."""
        result = _run(["uv", "run", "ruff", "check", "--isolated", "--select", "S101", "bot/"])
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"expected 0, got {result.returncode}: {combined[:1500]}"
        assert "All checks passed" in combined, f"expected All checks passed, got: {combined[:1500]}"

    def test_isolated_s310_zero_after_fix(self) -> None:
        """Post-fix: isolated S310 must be 0 (RED was 2 — urlopen in image_service)."""
        result = _run(["uv", "run", "ruff", "check", "--isolated", "--select", "S310", "bot/"])
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"S310 still present: {combined[:1500]}"
        assert "All checks passed" in combined or result.returncode == 0

    def test_isolated_s311_zero_after_fix(self) -> None:
        """Post-fix: isolated S311 must be 0 (RED was 2 — random in ocio)."""
        result = _run(["uv", "run", "ruff", "check", "--isolated", "--select", "S311", "bot/"])
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"S311 still present: {combined[:1500]}"
        assert "All checks passed" in combined or result.returncode == 0

    def test_isolated_s110_zero_after_fix(self) -> None:
        """Post-fix: isolated S110 must be 0 (RED was 1 — try-except-pass in config)."""
        result = _run(["uv", "run", "ruff", "check", "--isolated", "--select", "S110", "bot/"])
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"S110 still present: {combined[:1500]}"
        assert "All checks passed" in combined or result.returncode == 0

    def test_isolated_s_all_zero_after_fix(self) -> None:
        """Post-fix: isolated S (bandit/security) must be 0 (RED was 97)."""
        result = _run(["uv", "run", "ruff", "check", "--isolated", "--select", "S", "bot/"])
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"isolated S should exit 0, got {result.returncode}: {combined[:1500]}"
        assert "All checks passed" in combined, f"expected All checks passed, got: {combined[:1500]}"


# ---------------------------------------------------------------------------
# 4b.2 Remove S from bot/**/*.py per-file-ignores (progressive removal)
# ---------------------------------------------------------------------------


class TestPerFileIgnoresSecurityRemoved:
    """4b.2 RED: bot/**/*.py must NOT suppress S after PR4b."""

    def _bot_ignores(self) -> list[str]:
        data = _load_pyproject()
        per = data.get("tool", {}).get("ruff", {}).get("lint", {}).get("per-file-ignores", {})
        return per.get("bot/**/*.py", [])

    def test_bot_ignores_no_s_broad(self) -> None:
        ignores = self._bot_ignores()
        assert "S" not in ignores, f"bot/**/*.py still suppresses S (bandit): {ignores}"

    def test_bot_ignores_no_s101(self) -> None:
        ignores = self._bot_ignores()
        assert "S101" not in ignores, f"bot/**/*.py still suppresses S101: {ignores}"

    def test_bot_ignores_no_s310(self) -> None:
        ignores = self._bot_ignores()
        assert "S310" not in ignores, f"bot/**/*.py still suppresses S310: {ignores}"

    def test_bot_ignores_no_s311(self) -> None:
        ignores = self._bot_ignores()
        assert "S311" not in ignores, f"bot/**/*.py still suppresses S311: {ignores}"

    def test_bot_ignores_no_s110(self) -> None:
        ignores = self._bot_ignores()
        assert "S110" not in ignores, f"bot/**/*.py still suppresses S110: {ignores}"

    def test_bot_ignores_retains_quality_suppressions(self) -> None:
        """Progressive removal must keep PR4c suppressions (C4/C90/ARG/etc.) — or be clean after PR4c."""
        ignores = self._bot_ignores()
        # After PR4c, bot/** is preview-only (ANN/RUF) — the 14 quality codes are gone. Accept either state.
        if ignores == ["ANN", "RUF052", "RUF029", "RUF069", "RUF050", "RUF100"] or set(ignores).issubset({
            "ANN",
            "RUF052",
            "RUF029",
            "RUF069",
            "RUF050",
            "RUF100",
        }):
            return
        for must_keep in ["C4", "C90", "T20", "ARG", "DTZ", "T10", "TRY004", "TRY300", "FURB"]:
            assert must_keep in ignores, f"bot/**/*.py missing expected retained {must_keep}: {ignores}"


# ---------------------------------------------------------------------------
# 4b.3 GREEN S101: no assert in bot/ after rewrite (raise ValueError / if)
# ---------------------------------------------------------------------------


class TestRuffSecurityGreenS101:
    """4b.3 GREEN: after rewrite, `ruff check --select S101 bot/` is 0 and
    no `assert ` remains in bot/**/*.py (except scoped noqa cases).
    """

    def test_no_assert_remains_in_bot(self) -> None:
        """No `assert ` statement should remain in bot/**/*.py after S101 fix.
        Narrow `noqa: S101` is allowed only when dispositioned — but PR4b
        converts all S101 to real raises, so `assert ` must be 0.
        """
        pattern = re.compile(r"^\s*assert\b", re.MULTILINE)
        offenders: list[str] = []
        for p in PROJECT_ROOT.glob("bot/**/*.py"):
            text = p.read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), 1):
                if pattern.search(line) and "# noqa" not in line:
                    offenders.append(f"{p.relative_to(PROJECT_ROOT)}:{i}: {line.strip()}")
        assert offenders == [], f"assert remains in bot/** after S101 fix (expected 0): {offenders[:20]}"

    def test_ruff_s101_bot_zero(self) -> None:
        result = _run(["uv", "run", "ruff", "check", "--select", "S101", "bot/"])
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"S101 still present via normal ruff: {combined[:1500]}"
        assert "All checks passed" in combined or combined.strip() == "", (
            f"expected All checks passed: {combined[:1500]}"
        )

    def test_full_ruff_still_green(self) -> None:
        result = _run(["uv", "run", "ruff", "check", "bot/"])
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"ruff check bot/ failed after S fix: {combined[:1500]}"


# ---------------------------------------------------------------------------
# 4b.4 GREEN S310/S311/S110: case-by-case dispositioned
# ---------------------------------------------------------------------------


class TestRuffSecurityGreenOthers:
    """4b.4 GREEN: S310/S311/S110 dispositioned (fixed or narrow noqa with reason)."""

    def test_ruff_s310_bot_zero_or_narrow_noqa(self) -> None:
        result = _run(["uv", "run", "ruff", "check", "--select", "S310", "bot/"])
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"S310 not dispositioned: {combined[:1500]}"

    def test_ruff_s311_bot_zero_or_narrow_noqa(self) -> None:
        result = _run(["uv", "run", "ruff", "check", "--select", "S311", "bot/"])
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"S311 not dispositioned: {combined[:1500]}"

    def test_ruff_s110_bot_zero(self) -> None:
        result = _run(["uv", "run", "ruff", "check", "--select", "S110", "bot/"])
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"S110 not fixed: {combined[:1500]}"


# ---------------------------------------------------------------------------
# 4b.5 Keep tests/** S101/ARG/T20 semantic ignores (tests must still have them)
# ---------------------------------------------------------------------------


class TestTestsIgnoresPreserved:
    """4b.5 Keep tests/** semantic ignores — S101/ARG/T20 exception for tests."""

    def _tests_ignores(self) -> list[str]:
        data = _load_pyproject()
        per = data.get("tool", {}).get("ruff", {}).get("lint", {}).get("per-file-ignores", {})
        return per.get("tests/**/*.py", [])

    def test_tests_ignores_has_s101(self) -> None:
        ignores = self._tests_ignores()
        assert "S101" in ignores, f"tests/**/*.py missing S101 semantic ignore: {ignores}"

    def test_tests_ignores_has_arg(self) -> None:
        ignores = self._tests_ignores()
        assert "ARG" in ignores, f"tests/**/*.py missing ARG ignore: {ignores}"

    def test_tests_ignores_has_t20(self) -> None:
        ignores = self._tests_ignores()
        assert "T20" in ignores, f"tests/**/*.py missing T20 ignore: {ignores}"
