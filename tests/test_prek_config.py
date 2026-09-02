"""prek config twins (tests-slim-fase-2 B2) — replaces tests/test_pr3_prek_replaces_precommit.py.

Lean twin: prek.toml existence/priorities, builtin + local hook contracts,
ordering, and subprocess behavior via ``_run_prek``. The survivor's 21 tests
compress via parametrize; every hook NAME and ordering assertion is preserved.

Cold-start rationale (flake engram #5037): cold ``uvx prek`` exceeds 60s, so
``_run_prek`` pre-warms with ``uvx prek --help`` (timeout=60) then runs with
timeout=120 per design D4.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PREK_TOML = PROJECT_ROOT / "prek.toml"
PRECOMMIT_YAML = PROJECT_ROOT / ".pre-commit-config.yaml"


def _load_prek() -> dict:
    with open(PREK_TOML, "rb") as f:
        return tomllib.load(f)


def _run_prek(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    """Run ``uvx prek <args>`` with cold-start pre-warm (D4, flake #5037)."""
    subprocess.run(["uvx", "prek", "--help"], capture_output=True, timeout=60, cwd=str(PROJECT_ROOT))  # noqa: S607 -- uvx resolved via PATH like the deleted survivor
    merged = os.environ.copy()
    return subprocess.run(
        ["uvx", "prek", *args],  # noqa: S607 -- uvx resolved via PATH like the deleted survivor
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        env=merged,
        timeout=timeout,
    )


def _has_betterleaks() -> bool:
    return shutil.which("betterleaks") is not None


def _betterleaks_guard(combined: str) -> bool:
    """Return True when the run is blocked by missing betterleaks (CI qa-matrix)."""
    low = combined.lower()
    return not _has_betterleaks() and "betterleaks" in low and "no such file" in low


# ---------------------------------------------------------------------------
# Config existence + single source
# ---------------------------------------------------------------------------


class TestPrekConfigPresence:
    def test_prek_toml_exists(self) -> None:
        assert PREK_TOML.exists(), "prek.toml must exist at repo root"

    def test_prek_is_single_source(self) -> None:
        assert PREK_TOML.exists()
        assert not PRECOMMIT_YAML.exists(), "both configs present — single source violated"


# ---------------------------------------------------------------------------
# Priorities (parametrized — order ladder preserved)
# ---------------------------------------------------------------------------


class TestPrekPriorities:
    @pytest.mark.parametrize(
        ("group", "expected"),
        [
            pytest.param("builtin", 0, id="prio-builtin-0"),
            pytest.param("format", 10, id="prio-format-10"),
            pytest.param("lint", 20, id="prio-lint-20"),
            pytest.param("type", 30, id="prio-type-30"),
            pytest.param("gga", 40, id="prio-gga-40"),
            pytest.param("push", 50, id="prio-push-50"),
        ],
    )
    def test_priorities_defined(self, group: str, expected: int) -> None:
        pri = _load_prek().get("priorities", {})
        assert pri.get(group) == expected, f"priority {group} must be {expected}, got {pri}"


# ---------------------------------------------------------------------------
# Builtin + local hook contracts (parametrized — every hook NAME preserved)
# ---------------------------------------------------------------------------


def _local_hooks() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for repo in _load_prek().get("repos", []):
        if repo.get("repo") == "local":
            for h in repo.get("hooks", []):
                out[h["id"]] = h
    return out


class TestPrekBuiltin:
    def test_builtin_repo_has_four_hooks(self) -> None:
        data = _load_prek()
        builtin = next(r for r in data["repos"] if r.get("repo") == "builtin")
        ids = [h["id"] for h in builtin.get("hooks", [])]
        for expected in ["trailing-whitespace", "end-of-file-fixer", "check-yaml", "check-added-large-files"]:
            assert expected in ids, f"builtin missing {expected}, got {ids}"

    @pytest.mark.parametrize("hid", ["trailing-whitespace", "end-of-file-fixer"], ids=["ws", "eof"])
    def test_builtin_exclusions_preserved(self, hid: str) -> None:
        data = _load_prek()
        builtin = next(r for r in data["repos"] if r.get("repo") == "builtin")
        hooks_by_id = {h["id"]: h for h in builtin.get("hooks", [])}
        excl = hooks_by_id[hid].get("exclude", "")
        assert "archive" in excl, f"{hid} missing archive exclude: {excl}"
        assert ".md" in excl, f"{hid} missing .md exclude: {excl}"
        assert ".json" in excl, f"{hid} missing .json exclude: {excl}"


class TestPrekLocalHooks:
    @pytest.mark.parametrize(
        ("hid", "entry_fragment", "priority"),
        [
            pytest.param("ruff-check", "uv run ruff check --fix", "lint", id="hook-ruff-check"),
            pytest.param("ruff-format", "uv run ruff format --check", "format", id="hook-ruff-format"),
            pytest.param("ty", "uv run ty check bot/ tests/", "type", id="hook-ty"),
            pytest.param("gga", "bash .gga", "gga", id="hook-gga"),
        ],
    )
    def test_local_hook_contract(self, hid: str, entry_fragment: str, priority: str) -> None:
        hooks = _local_hooks()
        h = hooks.get(hid)
        assert h is not None, f"missing {hid}, got {list(hooks.keys())}"
        assert entry_fragment in h.get("entry", ""), f"{hid} entry wrong: {h}"
        assert h.get("priority") == priority, f"{hid} priority must be {priority}, got {h.get('priority')}"
        assert "pre-commit" in h.get("stages", []), f"{hid} stages wrong: {h}"

    def test_ruff_hooks_scope_files(self) -> None:
        hooks = _local_hooks()
        for hid in ["ruff-check", "ruff-format"]:
            files = hooks[hid].get("files", "")
            assert "bot/" in files and "tests/" in files, f"{hid} files wrong: {files}"

    def test_gga_always_run_no_filenames(self) -> None:
        h = _local_hooks()["gga"]
        assert h.get("always_run") is True, f"gga always_run must be true: {h}"
        assert h.get("pass_filenames") is False, f"gga pass_filenames must be false: {h}"

    def test_hook_ordering_ruff_before_ty_before_gga(self) -> None:
        # effective order must be ruff-check/format before ty before gga
        ordered: list[str] = []
        for repo in _load_prek().get("repos", []):
            if repo.get("repo") == "local":
                for h in repo.get("hooks", []):
                    if h.get("stages") == ["pre-push"]:
                        continue
                    ordered.append(h["id"])
        assert ordered.index("ruff-check") < ordered.index("ty"), f"ruff-check must be before ty: {ordered}"
        assert ordered.index("ruff-format") < ordered.index("ty"), f"ruff-format must be before ty: {ordered}"
        assert ordered.index("ty") < ordered.index("gga"), f"ty must be before gga: {ordered}"


class TestPrekPrePush:
    @pytest.mark.parametrize(
        ("hid", "entry_fragment"),
        [
            pytest.param("uv-lock-check", "uv lock --check", id="prepush-uv-lock-check"),
            pytest.param("tach-check", "tach check", id="prepush-tach-check"),
            pytest.param("tach-check-external", "tach check-external", id="prepush-tach-check-external"),
        ],
    )
    def test_prepush_hook_contract(self, hid: str, entry_fragment: str) -> None:
        hooks = {
            h["id"]: h
            for repo in _load_prek().get("repos", [])
            if repo.get("repo") == "local"
            for h in repo.get("hooks", [])
            if "pre-push" in h.get("stages", [])
        }
        h = hooks.get(hid)
        assert h is not None, f"missing {hid} pre-push, got {list(hooks.keys())}"
        assert entry_fragment in h.get("entry", ""), f"{hid} entry wrong: {h}"
        assert h.get("always_run") is True
        assert h.get("pass_filenames") is False
        assert "pre-push" in h.get("stages", [])
        assert h.get("priority") == "push"

    def test_no_pytest_in_precommit(self) -> None:
        all_ids: list[str] = []
        for repo in _load_prek().get("repos", []):
            for h in repo.get("hooks", []):
                if "pre-commit" in h.get("stages", ["pre-commit"]):
                    all_ids.append(h["id"])
        for bad in ["pytest", "test", "tests"]:
            assert not any(bad == i for i in all_ids), f"tests must not run per-commit, found {bad} in {all_ids}"


# ---------------------------------------------------------------------------
# Subprocess behavior — _run_prek (120s + pre-warm per design D4)
# ---------------------------------------------------------------------------


class TestPrekHookBehavior:
    def test_prek_validate_config(self) -> None:
        result = _run_prek(["validate-config", str(PREK_TOML)])
        assert result.returncode == 0, f"prek validate-config failed: {result.stdout}{result.stderr}"

    def test_prek_run_all_files_exits_zero(self) -> None:
        result = _run_prek(["run", "--all-files", "--no-progress"])
        combined = result.stdout + result.stderr
        if _betterleaks_guard(combined):
            return
        assert result.returncode == 0, f"prek run --all-files failed: {combined[:2000]}"

    def test_trailing_whitespace_hook_blocks(self) -> None:
        scratch = PROJECT_ROOT / "tests" / "_tmp_prek_trailing_ws.py"
        try:
            scratch.write_text("x = 1   \n", encoding="utf-8")
            result = _run_prek(["run", "--files", str(scratch), "--no-progress"])
            combined = result.stdout + result.stderr
            if _betterleaks_guard(combined):
                return
            assert result.returncode != 0, f"prek should fail on trailing ws: {combined[:2000]}"
            low = combined.lower()
            assert "trailing" in low, f"expected trailing failure, got: {combined[:2000]}"
        finally:
            if scratch.exists():
                scratch.unlink()
