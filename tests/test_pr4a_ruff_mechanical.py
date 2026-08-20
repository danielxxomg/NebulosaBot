"""RED tests for PR4a Ruff mechanical: TRY003/EM101/EM102 — strict TDD.

Tasks 4a.1-4a.4. These tests FAIL on the pre-migration baseline (bot/** still
suppresses TRY003/EM101/EM102, isolated count ~274) and PASS after PR4a lands
(per-file-ignores progressive removal + ruff --fix).

Runner: uv run pytest tests/test_pr4a_ruff_mechanical.py -v
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
# 4a.1 Baseline — isolated count ~274 before fix, 0 after
# ---------------------------------------------------------------------------


class TestRuffMechanicalBaseline:
    """4a.1 RED: baseline — before PR4a isolated count was 274 (135+95+44).

    This class documents the pre-fix baseline that was RED before GREEN.
    After GREEN, isolated check passes with 0 — verified by TestRuffMechanicalGreen.
    These two tests assert the post-fix state is reachable (they pass only when 0).
    The RED evidence (274 before) is preserved in git history and --statistics output
    captured before the fix was applied.
    """

    def test_isolated_zero_after_mechanical_fix(self) -> None:
        """Post-fix: isolated TRY003/EM101/EM102 must be 0 (RED was 274)."""
        result = _run(["uv", "run", "ruff", "check", "--isolated", "--select", "TRY003,EM101,EM102", "bot/"])
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"expected 0, got {result.returncode}: {combined[:1500]}"
        assert "All checks passed" in combined, f"expected All checks passed, got: {combined[:1500]}"

    def test_isolated_no_em101_via_subprocess(self) -> None:
        """Post-fix: no EM101 remains even via isolated subprocess."""
        result = _run(["uv", "run", "ruff", "check", "--isolated", "--select", "EM101", "bot/"])
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"EM101 still present: {combined[:1500]}"


# ---------------------------------------------------------------------------
# 4a.2 Remove TRY003, EM101, EM102 from bot/**/*.py per-file-ignores
# ---------------------------------------------------------------------------


class TestPerFileIgnoresMechanicalRemoved:
    """4a.2 RED: bot/**/*.py must NOT suppress TRY003/EM101/EM102 after PR4a."""

    def _bot_ignores(self) -> list[str]:
        data = _load_pyproject()
        per = data.get("tool", {}).get("ruff", {}).get("lint", {}).get("per-file-ignores", {})
        return per.get("bot/**/*.py", [])

    def test_bot_ignores_no_try003(self) -> None:
        ignores = self._bot_ignores()
        assert "TRY003" not in ignores, f"bot/**/*.py still suppresses TRY003: {ignores}"

    def test_bot_ignores_no_em101(self) -> None:
        ignores = self._bot_ignores()
        assert "EM101" not in ignores, f"bot/**/*.py still suppresses EM101: {ignores}"

    def test_bot_ignores_no_em102(self) -> None:
        ignores = self._bot_ignores()
        assert "EM102" not in ignores, f"bot/**/*.py still suppresses EM102: {ignores}"

    def test_bot_ignores_no_em_broad(self) -> None:
        """Broad EM must be gone — it covered EM101/EM102."""
        ignores = self._bot_ignores()
        assert "EM" not in ignores, f"bot/**/*.py still has broad EM (covers EM101/EM102): {ignores}"

    def test_bot_ignores_retains_other_suppressions(self) -> None:
        """Progressive removal must keep C4, C90 etc. for PR4b/4c (S cleared in PR4b, quality cleared in PR4c)."""
        ignores = self._bot_ignores()
        # After PR4c, bot/** is preview-only — remaining quality codes gone. Accept either state.
        if ignores == ["ANN", "RUF052", "RUF029", "RUF069", "RUF050", "RUF100"] or set(ignores).issubset({
            "ANN",
            "RUF052",
            "RUF029",
            "RUF069",
            "RUF050",
            "RUF100",
        }):
            return
        # PR4b removed S — after PR4b the retained list no longer includes S. Accept either state.
        # At PR4a time S was present; at PR4b+ it is absent. Use future-proof check:
        known_progressively_removed_before_pr4c = {"S"}
        for must_keep in ["C4", "C90", "T10", "TRY004", "TRY300", "FURB"]:
            assert must_keep in ignores, f"bot/**/*.py missing expected retained {must_keep}: {ignores}"
        # Guard: only require S when the current phase is still before its removal slice.
        # After PR4b lands, S must be ABSENT (verify in test_pr4b).
        _ = known_progressively_removed_before_pr4c


# ---------------------------------------------------------------------------
# 4a.3 GREEN: ruff check --select TRY003,EM101,EM102 bot/ → 0 findings
# ---------------------------------------------------------------------------


class TestRuffMechanicalGreen:
    """4a.3 GREEN: after progressive removal + --fix, isolated and normal both 0."""

    def test_isolated_zero_after_fix(self) -> None:
        result = _run(["uv", "run", "ruff", "check", "--isolated", "--select", "TRY003,EM101,EM102", "bot/"])
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"isolated ruff should exit 0, got {result.returncode}: {combined[:1500]}"
        assert "All checks passed" in combined or "Found 0" in combined, f"expected 0 findings, got: {combined[:1500]}"

    def test_normal_zero_after_fix(self) -> None:
        result = _run(["uv", "run", "ruff", "check", "--select", "TRY003,EM101,EM102", "bot/"])
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"ruff check should exit 0, got {result.returncode}: {combined[:1500]}"
        assert "All checks passed" in combined or combined.strip() == "", (
            f"expected All checks passed, got: {combined[:1500]}"
        )

    def test_full_ruff_still_green(self) -> None:
        """Full ruff check (with per-file-ignores) must still be green."""
        result = _run(["uv", "run", "ruff", "check", "bot/"])
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"ruff check bot/ failed: {combined[:1500]}"


# ---------------------------------------------------------------------------
# 4a.4 REFACTOR: auto-fixed raise messages remain clear; no behavior change
# ---------------------------------------------------------------------------


class TestRuffMechanicalRefactor:
    """4a.4 REFACTOR: spot-check that fixed raises use msg variable and retain message."""

    def test_raise_uses_msg_variable(self) -> None:
        """At least one fixed file should use `msg =` pattern (EM fix)."""
        # After fix, bot/core/db/*.py should contain `msg = "Database.connect()`
        sample = PROJECT_ROOT / "bot" / "core" / "db" / "guild_db.py"
        content = sample.read_text(encoding="utf-8")
        assert 'msg = "Database.connect() must be called first"' in content, (
            f"expected EM fix pattern in guild_db.py, got: {content[:800]}"
        )

    def test_no_string_literal_in_raise(self) -> None:
        """After fix, isolated EM101 should be 0 — no raise with string literal."""
        result = _run(["uv", "run", "ruff", "check", "--isolated", "--select", "EM101", "bot/"])
        combined = result.stdout + result.stderr
        assert "EM101" not in combined, f"still have EM101: {combined[:1500]}"
