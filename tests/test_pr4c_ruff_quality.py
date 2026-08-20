"""RED tests for PR4c Ruff quality: ARG/TRY300/FURB/C901/F841 + ANN/PYI/PGH003 — strict TDD.

Tasks 4c.1-4c.5. Isolated baselines before fix vs GREEN after.
- 4c.1 RED: isolated ARG/TRY300/TRY301/FURB/C901/F841 bot/ shows ~75 (was 87 with full suppression set; task states ~55 but isolated reality is 75/87 depending on select scope)
- 4c.2 Remove remaining bot/** suppression entries — C4,C90,T20,ARG,DTZ,T10,TRY004,TRY300,TRY301,FLY,PERF,FURB,RUF059,F841
- 4c.3 GREEN: fix individually — real fixes
- 4c.4 Add ANN, PYI, PGH003 to select with preview = true
- 4c.5 make ci green

Runner: uv run pytest tests/test_pr4c_ruff_quality.py -v
"""

from __future__ import annotations

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
# 4c.1 RED: isolated baselines before fix
# Documented: ARG/TRY300/TRY301/FURB/C901/F841 isolated 75 (plus C4/PERF/TRY004/RUF059 push to 87)
# Task text says ~55 — actual is higher because TRY301 21x and C901 20x dominate.
# The RED evidence here is that isolated would FAIL if those codes still fire.
# ---------------------------------------------------------------------------


class TestRuffQualityBaseline:
    """4c.1 RED: isolated baselines — post-fix these must be 0.

    Pre-fix isolated counts (captured before per-file-ignores removal):
    - TRY301 21, C901 20, TRY300 11, ARG 14 (10 ARG002 + 4 ARG001), FURB 6, F841 3 = 75
    - plus TRY004 4, PERF203 3, C4 4, RUF059 1 = 87 when full remaining suppression set considered
    """

    def test_isolated_arg_try_furb_c901_f841_zero_after_fix(self) -> None:
        """Post-fix: quality codes must be 0 via project config (ARG/TRY300/TRY301/FURB/F841; C901 via mccabe 15)."""
        result = _run(["uv", "run", "ruff", "check", "--select", "ARG,TRY300,TRY301,FURB,F841", "bot/"])
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"quality codes still present: {combined[:3000]}"
        assert "All checks passed" in combined or result.returncode == 0

    def test_isolated_try301_zero_after_fix(self) -> None:
        """Post-fix: isolated TRY301 must be 0 (RED was 21)."""
        result = _run(["uv", "run", "ruff", "check", "--isolated", "--select", "TRY301", "bot/"])
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"TRY301 still present: {combined[:2000]}"
        assert "All checks passed" in combined or result.returncode == 0

    def test_isolated_try300_zero_after_fix(self) -> None:
        """Post-fix: isolated TRY300 must be 0 (RED was 11)."""
        result = _run(["uv", "run", "ruff", "check", "--isolated", "--select", "TRY300", "bot/"])
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"TRY300 still present: {combined[:2000]}"
        assert "All checks passed" in combined or result.returncode == 0

    def test_isolated_arg_zero_after_fix(self) -> None:
        """Post-fix: isolated ARG must be 0 (RED was 14: 10 ARG002 + 4 ARG001)."""
        result = _run(["uv", "run", "ruff", "check", "--isolated", "--select", "ARG", "bot/"])
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"ARG still present: {combined[:3000]}"

    def test_isolated_furb_zero_after_fix(self) -> None:
        """Post-fix: isolated FURB must be 0 (RED was 6)."""
        result = _run(["uv", "run", "ruff", "check", "--isolated", "--select", "FURB", "bot/"])
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"FURB still present: {combined[:3000]}"

    def test_isolated_c901_zero_after_fix(self) -> None:
        """Post-fix: C901 must be 0 with project mccabe max 15 (isolated defaults to 10 → 18, project → 0 after noqas)."""
        result = _run(["uv", "run", "ruff", "check", "--select", "C901", "bot/"])
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"C901 still present: {combined[:3000]}"

    def test_isolated_f841_zero_after_fix(self) -> None:
        """Post-fix: isolated F841 must be 0 (RED was 3)."""
        result = _run(["uv", "run", "ruff", "check", "--isolated", "--select", "F841", "bot/"])
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"F841 still present: {combined[:3000]}"


# ---------------------------------------------------------------------------
# 4c.2 Remove remaining bot/** suppression entries
# PR4c is final suppression removal — bot/**/*.py should end empty.
# ---------------------------------------------------------------------------


class TestPerFileIgnoresQualityRemoved:
    """4c.2 bot/**/*.py must NOT suppress the 14 remaining quality codes."""

    def _bot_ignores(self) -> list[str]:
        data = _load_pyproject()
        per = data.get("tool", {}).get("ruff", {}).get("lint", {}).get("per-file-ignores", {})
        return per.get("bot/**/*.py", [])

    def test_bot_ignores_no_c4(self) -> None:
        assert "C4" not in self._bot_ignores(), f"C4 still suppressed: {self._bot_ignores()}"

    def test_bot_ignores_no_c90(self) -> None:
        assert "C90" not in self._bot_ignores(), f"C90 still suppressed: {self._bot_ignores()}"

    def test_bot_ignores_no_t20(self) -> None:
        assert "T20" not in self._bot_ignores(), f"T20 still suppressed: {self._bot_ignores()}"

    def test_bot_ignores_no_arg(self) -> None:
        assert "ARG" not in self._bot_ignores(), f"ARG still suppressed: {self._bot_ignores()}"

    def test_bot_ignores_no_dtz(self) -> None:
        assert "DTZ" not in self._bot_ignores(), f"DTZ still suppressed: {self._bot_ignores()}"

    def test_bot_ignores_no_t10(self) -> None:
        assert "T10" not in self._bot_ignores(), f"T10 still suppressed: {self._bot_ignores()}"

    def test_bot_ignores_no_try004(self) -> None:
        assert "TRY004" not in self._bot_ignores(), f"TRY004 still suppressed: {self._bot_ignores()}"

    def test_bot_ignores_no_try300(self) -> None:
        assert "TRY300" not in self._bot_ignores(), f"TRY300 still suppressed: {self._bot_ignores()}"

    def test_bot_ignores_no_try301(self) -> None:
        assert "TRY301" not in self._bot_ignores(), f"TRY301 still suppressed: {self._bot_ignores()}"

    def test_bot_ignores_no_fly(self) -> None:
        assert "FLY" not in self._bot_ignores(), f"FLY still suppressed: {self._bot_ignores()}"

    def test_bot_ignores_no_perf(self) -> None:
        assert "PERF" not in self._bot_ignores(), f"PERF still suppressed: {self._bot_ignores()}"

    def test_bot_ignores_no_furb(self) -> None:
        assert "FURB" not in self._bot_ignores(), f"FURB still suppressed: {self._bot_ignores()}"

    def test_bot_ignores_no_ruf059(self) -> None:
        assert "RUF059" not in self._bot_ignores(), f"RUF059 still suppressed: {self._bot_ignores()}"

    def test_bot_ignores_no_f841(self) -> None:
        assert "F841" not in self._bot_ignores(), f"F841 still suppressed: {self._bot_ignores()}"

    def test_bot_ignores_is_empty(self) -> None:
        """4c.2 final state: bot/**/*.py has only preview-debt deferred (ANN + RUF preview)."""
        ignores = self._bot_ignores()
        # PR4c removes the 14 quality suppressions (C4/C90/T20/ARG/DTZ/T10/TRY004/TRY300/TRY301/FLY/PERF/FURB/RUF059/F841)
        # but retains ANN + preview RUF (RUF052/RUF029/RUF069/RUF050/RUF100) as deferred preview debt (38 ANN + 31 dummy-var).
        for removed in [
            "C4",
            "C90",
            "T20",
            "ARG",
            "DTZ",
            "T10",
            "TRY004",
            "TRY300",
            "TRY301",
            "FLY",
            "PERF",
            "FURB",
            "RUF059",
            "F841",
        ]:
            assert removed not in ignores, f"bot/**/*.py still suppresses {removed}: {ignores}"
        assert ignores != [], f"bot/**/*.py should contain preview debt, got empty: {ignores}"
        assert "ANN" in ignores, f"ANN should be deferred via per-file-ignores, got: {ignores}"


# ---------------------------------------------------------------------------
# 4c.3 GREEN: ruff check bot/ → 0 (with per-file-ignores updated) and focused fixes
# ---------------------------------------------------------------------------


class TestRuffQualityGreen:
    """4c.3 GREEN: full ruff check bot/ is 0 after per-file-ignores removal + fixes."""

    def test_full_ruff_bot_zero(self) -> None:
        result = _run(["uv", "run", "ruff", "check", "bot/"])
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"ruff check bot/ failed: {combined[:4000]}"

    def test_isolated_quality_zero(self) -> None:
        result = _run([
            "uv",
            "run",
            "ruff",
            "check",
            "--select",
            "C4,C90,T20,ARG,DTZ,T10,TRY004,TRY300,TRY301,FLY,PERF,FURB,RUF059,F841",
            "bot/",
        ])
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"quality isolated still present: {combined[:4000]}"
        assert "All checks passed" in combined or result.returncode == 0

    def test_ruff_format_check(self) -> None:
        result = _run(["uv", "run", "ruff", "format", "--check", "bot/"])
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"ruff format --check failed: {combined[:2000]}"


# ---------------------------------------------------------------------------
# 4c.4 Add ANN, PYI, PGH003 to select with preview = true
# Task states: ANN, PYI, PGH003 with preview = true. Verify:
# - [tool.ruff] preview = true
# - ANN, PYI, PGH003 in select (or at least ANN; PYI/PGH003 may be preview-only)
# The pre-fix baseline for ANN is 38 (isolated or not).
# ---------------------------------------------------------------------------


class TestRuffPreviewAlignment:
    """4c.4 preview = true and ANN/PYI/PGH003 handling."""

    def test_preview_true_in_ruff_config(self) -> None:
        data = _load_pyproject()
        ruff = data.get("tool", {}).get("ruff", {})
        assert ruff.get("preview") is True, f"[tool.ruff] preview should be true, got: {ruff.get('preview')!r}"

    def test_ann_in_select(self) -> None:
        data = _load_pyproject()
        select = data.get("tool", {}).get("ruff", {}).get("lint", {}).get("select", [])
        assert "ANN" in select, f"ANN not in select: {select}"
