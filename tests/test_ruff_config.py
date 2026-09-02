"""Ruff config tests (tests-slim-fase-2 B3) — host + twins replacing test_pr4a/b/c.

Host (pyproject-toml-qa): select groups, mccabe 15, tests/ ignores S101/ARG/T20
(host also covers survivor 4b.5 tests-ignores preservation). Twins compress 623
survivor lines via shared `_run_ruff` helper: mechanical TRY003/EM101/EM102
isolated 0 + EM msg-pattern retained (4a); security S101/S310/S311/S110 isolated
0, S-all 0, no bare assert (4b); quality ARG/TRY300/TRY301/FURB/F841/C901 0 +
format check (4c); per-file-ignores meta-guard (bot/** progressive removal,
preview debt retained) + preview alignment (4a.2/4b.2/4c.2/4c.4).
Parametrize ids carry the rule-code coverage names (D2/D3).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PYPROJECT = _PROJECT_ROOT / "pyproject.toml"
# Absolute path avoids S607 (partial executable path) without a pyproject ignore.
_UV = shutil.which("uv") or "/usr/local/bin/uv"
_PREVIEW_DEBT = ["ANN", "RUF052", "RUF029", "RUF069", "RUF050", "RUF100"]
# 14 tooling-rigor groups + 9 original groups enforced by the host spec.
_SELECT_GROUPS = [
    "S",
    "C4",
    "C90",
    "RET",
    "T20",
    "ARG",
    "DTZ",
    "EM",
    "T10",
    "TRY",
    "RSE",
    "FLY",
    "PERF",
    "FURB",
    "E",
    "W",
    "F",
    "I",
    "N",
    "UP",
    "B",
    "SIM",
    "RUF",
]


def _load_pyproject() -> dict[str, Any]:
    with open(_PYPROJECT, "rb") as f:
        return tomllib.load(f)


def _per_file_ignores(glob: str) -> list[str]:
    per = _load_pyproject().get("tool", {}).get("ruff", {}).get("lint", {}).get("per-file-ignores", {})
    for key, val in per.items():
        if glob in key:
            return val
    return []


def _run_ruff(select: str, *flags: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_UV, "run", "ruff", "check", *flags, "--select", select, "bot/"],
        cwd=str(_PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )


def _assert_zero(result: subprocess.CompletedProcess[str], label: str) -> None:
    combined = result.stdout + result.stderr
    assert result.returncode == 0, f"{label} still present: {combined[:1500]}"


# Host: select groups (14 new + 9 original), mccabe, tests/ ignores (4b.5)


class TestRuffSelectGroups:
    """Ruff select MUST include all tooling-rigor and original rule groups."""

    @pytest.mark.parametrize("group", _SELECT_GROUPS, ids=lambda g: f"select-has-{g}")
    def test_select_includes_group(self, group: str) -> None:
        select = _load_pyproject()["tool"]["ruff"]["lint"]["select"]
        assert group in select, f"Ruff select missing required group '{group}'. Current select: {select}"

    def test_max_complexity_is_15(self) -> None:
        mccabe = _load_pyproject()["tool"]["ruff"]["lint"].get("mccabe", {})
        assert mccabe.get("max-complexity") == 15, f"Expected max-complexity=15, got {mccabe.get('max-complexity')}"

    def test_tests_ignores_include_s101_arg_t20(self) -> None:
        ignores = _per_file_ignores("tests")
        for code in ("S101", "ARG", "T20"):
            assert code in ignores, f"{code} not in tests ignores: {ignores}"


# Twin: mechanical (survivor 4a — TRY003/EM101/EM102)


class TestRuffMechanicalTwin:
    @pytest.mark.parametrize("code", ["TRY003", "EM101", "EM102"], ids=lambda c: f"mech-isolated-zero-{c}")
    def test_isolated_mechanical_zero(self, code: str) -> None:
        _assert_zero(_run_ruff(code, "--isolated"), code)

    def test_mechanical_project_config_zero(self) -> None:
        _assert_zero(_run_ruff("TRY003,EM101,EM102"), "TRY003/EM101/EM102 (project config)")

    def test_em_fix_msg_pattern_retained(self) -> None:
        """EM101 --fix evidence: raises use `msg =` variable with the original message."""
        src = (_PROJECT_ROOT / "bot" / "core" / "db" / "guild_db.py").read_text(encoding="utf-8")
        assert 'msg = "Database.connect() must be called first"' in src


# Twin: security (survivor 4b — S101/S310/S311/S110)


class TestRuffSecurityTwin:
    @pytest.mark.parametrize("code", ["S101", "S310", "S311", "S110"], ids=lambda c: f"sec-isolated-zero-{c}")
    def test_isolated_security_zero(self, code: str) -> None:
        _assert_zero(_run_ruff(code, "--isolated"), code)

    def test_isolated_s_all_zero(self) -> None:
        _assert_zero(_run_ruff("S", "--isolated"), "S (bandit)")

    def test_no_assert_remains_in_bot(self) -> None:
        """S101 rewrite evidence: no bare `assert` statement remains in bot/**."""
        pattern = re.compile(r"^\s*assert\b", re.MULTILINE)
        offenders: list[str] = []
        for p in _PROJECT_ROOT.glob("bot/**/*.py"):
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line) and "# noqa" not in line:
                    offenders.append(f"{p.relative_to(_PROJECT_ROOT)}:{i}: {line.strip()}")
        assert offenders == [], f"assert remains in bot/** after S101 fix (expected 0): {offenders[:20]}"


# Twin: quality (survivor 4c — ARG/TRY300/TRY301/FURB/F841/C901)


class TestRuffQualityTwin:
    def test_isolated_quality_group_zero(self) -> None:
        _assert_zero(_run_ruff("ARG,TRY300,TRY301,FURB,F841", "--isolated"), "quality codes (isolated)")

    def test_c901_project_config_zero(self) -> None:
        """C901 with project mccabe max 15 (isolated default 10 would over-report)."""
        _assert_zero(_run_ruff("C901"), "C901 (mccabe 15)")

    def test_ruff_format_check(self) -> None:
        result = subprocess.run(
            [_UV, "run", "ruff", "format", "--check", "bot/"],
            cwd=str(_PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"ruff format --check failed: {result.stdout + result.stderr[:1500]}"

    def test_full_ruff_bot_zero(self) -> None:
        _assert_zero(_run_ruff(""), "full ruff check bot/")


# Twin: per-file-ignores meta-guard + preview alignment (4a.2/4b.2/4c.2/4c.4)


class TestRuffPerFileIgnoresMetaGuard:
    """Progressive removal end-state: bot/** keeps only preview debt (ANN + RUF)."""

    @pytest.mark.parametrize(
        "code",
        [
            "TRY003",
            "EM101",
            "EM102",
            "EM",
            "S",
            "S101",
            "S310",
            "S311",
            "S110",
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
        ],
        ids=lambda c: f"bot-ignores-no-{c}",
    )
    def test_bot_ignores_removed(self, code: str) -> None:
        assert code not in _per_file_ignores("bot/**/*.py"), f"bot/**/*.py still suppresses {code}"

    def test_bot_ignores_preview_debt_retained(self) -> None:
        ignores = _per_file_ignores("bot/**/*.py")
        assert ignores == _PREVIEW_DEBT, f"bot/**/*.py should be exactly preview debt, got: {ignores}"

    def test_preview_true_in_ruff_config(self) -> None:
        assert _load_pyproject().get("tool", {}).get("ruff", {}).get("preview") is True

    def test_ann_in_select(self) -> None:
        assert "ANN" in _load_pyproject()["tool"]["ruff"]["lint"]["select"]
