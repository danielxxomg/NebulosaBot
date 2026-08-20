"""RED tests for PR6 Tach Boundaries — strict TDD.

Tasks 6.1-6.8. Each test asserts the expected end-state before implementation.
RED before GREEN: these must fail until the slice is implemented.

Runner: uv run pytest tests/test_pr6_tach_boundaries.py -v
"""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
CI_YML = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
MAKEFILE = PROJECT_ROOT / "Makefile"
PREK_TOML = PROJECT_ROOT / "prek.toml"
TACH_TOML = PROJECT_ROOT / "tach.toml"
CORE_TICKET_REF = PROJECT_ROOT / "bot" / "core" / "ticket_ref.py"
SERVICES_INVARIANTS = PROJECT_ROOT / "bot" / "services" / "ticket_invariants.py"
TICKET_HELPERS = PROJECT_ROOT / "bot" / "utils" / "ticket_helpers.py"


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd or PROJECT_ROOT), capture_output=True, text=True, timeout=60)


def _load_toml(path: Path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


# ---------------------------------------------------------------------------
# 6.1 bot/core/ticket_ref.py with parse_ticket_ref + TicketRef
# ---------------------------------------------------------------------------


class TestTicketRefMove:
    """6.1 RED: bot/core/ticket_ref.py must exist and export parse_ticket_ref/TicketRef."""

    def test_core_ticket_ref_file_exists(self) -> None:
        assert CORE_TICKET_REF.exists(), "bot/core/ticket_ref.py missing — move not done"

    def test_core_ticket_ref_exports(self) -> None:
        from bot.core.ticket_ref import TicketRef, parse_ticket_ref

        assert TicketRef is not None
        assert parse_ticket_ref is not None
        # functional check
        ref = parse_ticket_ref("#0003")
        assert ref is not None
        assert ref.number == 3
        assert ref.uuid is None

    def test_core_ticket_ref_uuid(self) -> None:
        from bot.core.ticket_ref import parse_ticket_ref

        uuid_str = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        ref = parse_ticket_ref(uuid_str)
        assert ref is not None
        assert ref.uuid == uuid_str

    def test_core_ticket_ref_none_cases(self) -> None:
        from bot.core.ticket_ref import parse_ticket_ref

        assert parse_ticket_ref(None) is None
        assert parse_ticket_ref("") is None
        assert parse_ticket_ref("   ") is None
        assert parse_ticket_ref("not-a-ticket") is None

    def test_shim_keeps_importers_green(self) -> None:
        # 6.2 shim: imports via old path must still work and be same object
        from bot.core.ticket_ref import TicketRef as CoreRef
        from bot.core.ticket_ref import parse_ticket_ref as core_parse
        from bot.services.ticket_invariants import TicketRef as ServiceRef
        from bot.services.ticket_invariants import parse_ticket_ref as svc_parse

        assert CoreRef is ServiceRef, "shim must re-export same TicketRef"
        assert core_parse is svc_parse, "shim must re-export same parse_ticket_ref"

    def test_existing_ticket_tests_importable(self) -> None:
        # Ensure the two test suites that import via services still pass (shim green)
        result = _run([
            "uv",
            "run",
            "pytest",
            "tests/test_ticket_invariants.py",
            "tests/contract/test_ticket_invariants.py",
            "--no-cov",
            "-q",
        ])
        assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# 6.3 bot/utils/ticket_helpers.py imports from core not services
# ---------------------------------------------------------------------------


class TestTicketHelpersImport:
    """6.3 RED: ticket_helpers must import parse_ticket_ref from bot.core.ticket_ref."""

    def test_helpers_imports_core(self) -> None:
        content = TICKET_HELPERS.read_text()
        assert "from bot.core.ticket_ref import parse_ticket_ref" in content, content[:600]
        # Must NOT import from services (forbidden utils→services)
        assert "from bot.services.ticket_invariants import parse_ticket_ref" not in content, content[:600]

    def test_helpers_function_still_works(self) -> None:
        from bot.utils.ticket_helpers import resolve_ticket_for_reopen  # noqa: F401

        assert resolve_ticket_for_reopen is not None


# ---------------------------------------------------------------------------
# 6.4 tach.toml seven-layer architecture + strict flags + interfaces + external
# ---------------------------------------------------------------------------


class TestTachToml:
    """6.4 RED: tach.toml must declare 7 layers, 8 modules, interfaces, strict flags, external."""

    def test_tach_toml_exists(self) -> None:
        assert TACH_TOML.exists(), "tach.toml missing"

    def test_layers_seven_in_order(self) -> None:
        data = _load_toml(TACH_TOML)
        expected = ["cogs", "views", "services", "utils", "core", "db", "models"]
        assert data.get("layers") == expected, f"layers: {data.get('layers')}"

    def test_source_roots(self) -> None:
        data = _load_toml(TACH_TOML)
        assert data.get("source_roots") == ["."], f"source_roots: {data.get('source_roots')}"

    def test_strict_flags(self) -> None:
        data = _load_toml(TACH_TOML)
        assert data.get("exact") is True
        assert data.get("forbid_circular_dependencies") is True
        assert data.get("ignore_type_checking_imports") is True
        assert data.get("respect_gitignore") is True

    def test_root_module_ignore(self) -> None:
        data = _load_toml(TACH_TOML)
        assert data.get("root_module") == "ignore"

    def test_exclude_patterns(self) -> None:
        content = TACH_TOML.read_text()
        # must exclude cache/build/dist/dashboard/locales
        assert "__pycache__" in content
        assert "build/" in content
        assert "dist/" in content
        assert "dashboard/" in content
        assert "locales/" in content

    def test_eight_modules_declared(self) -> None:
        data = _load_toml(TACH_TOML)
        modules = data.get("modules") or []
        # tomllib parses [[modules]] as list
        assert len(modules) == 8, f"modules count {len(modules)}: {modules}"
        paths = {m["path"] for m in modules}
        expected_paths = {
            "bot.cogs",
            "bot.views",
            "bot.services",
            "bot.utils",
            "bot.listeners",
            "bot.core",
            "bot.core.db",
            "bot.models",
        }
        assert paths == expected_paths, f"paths: {paths}"
        # layer mapping
        layer_map = {m["path"]: m["layer"] for m in modules}
        assert layer_map["bot.cogs"] == "cogs"
        assert layer_map["bot.views"] == "views"
        assert layer_map["bot.services"] == "services"
        assert layer_map["bot.utils"] == "utils"
        assert layer_map["bot.listeners"] == "utils"
        assert layer_map["bot.core"] == "core"
        assert layer_map["bot.core.db"] == "db"
        assert layer_map["bot.models"] == "models"

    def test_interfaces_expose(self) -> None:
        data = _load_toml(TACH_TOML)
        interfaces = data.get("interfaces") or []
        assert len(interfaces) >= 2, f"interfaces: {interfaces}"
        # find core.ticket_ref interface
        core_int = [i for i in interfaces if "bot.core.ticket_ref" in str(i.get("from", []))]
        assert core_int, f"no bot.core.ticket_ref interface: {interfaces}"
        assert "parse_ticket_ref" in str(core_int[0].get("expose", []))
        assert "TicketRef" in str(core_int[0].get("expose", []))
        # find models interface
        models_int = [i for i in interfaces if "bot.models" in str(i.get("from", []))]
        assert models_int, f"no bot.models interface: {interfaces}"
        assert "Ticket" in str(models_int[0].get("expose", []))

    def test_external_exclude_rename(self) -> None:
        data = _load_toml(TACH_TOML)
        external = data.get("external") or {}
        exclude = external.get("exclude") or []
        assert "pytest" in exclude
        assert "hypothesis" in exclude
        assert "freezegun" in exclude
        rename = external.get("rename") or []
        assert "PIL:pillow" in rename
        assert "psycopg:psycopg" in rename

    def test_tach_check_passes(self) -> None:
        result = _run(["uv", "run", "tach", "check"])
        # uv run tach may need --with if not in dev; fallback to --with tach
        if "No such file" in result.stderr or "Failed to spawn" in result.stderr:
            result = _run(["uv", "run", "--with", "tach", "tach", "check"])
        assert result.returncode == 0, f"tach check failed: {result.stdout} {result.stderr}"

    def test_tach_check_external_passes(self) -> None:
        result = _run(["uv", "run", "tach", "check-external"])
        if "No such file" in result.stderr or "Failed to spawn" in result.stderr:
            result = _run(["uv", "run", "--with", "tach", "tach", "check-external"])
        assert result.returncode == 0, f"tach check-external failed: {result.stdout} {result.stderr}"


# ---------------------------------------------------------------------------
# 6.5 RED→GREEN tach boundary enforcement: models→cogs must fail
# ---------------------------------------------------------------------------


class TestTachBoundaryEnforcement:
    """6.5 RED: temp models→cogs import must be caught by tach check."""

    def test_models_to_cogs_violation_detected(self) -> None:
        ticket_py = PROJECT_ROOT / "bot" / "models" / "ticket.py"
        original = ticket_py.read_text()
        try:
            # Inject a forbidden import at top
            injected = "from bot.cogs.tickets import TicketsCog  # tach violation probe\n" + original
            ticket_py.write_text(injected)
            result = _run(["uv", "run", "tach", "check"])
            if "No such file" in result.stderr or "Failed to spawn" in result.stderr:
                result = _run(["uv", "run", "--with", "tach", "tach", "check"])
            assert result.returncode != 0, f"tach check should fail on models->cogs: {result.stdout} {result.stderr}"
            assert "bot.models" in result.stdout + result.stderr or "bot.cogs" in result.stdout + result.stderr, (
                result.stdout + result.stderr
            )
        finally:
            ticket_py.write_text(original)
            # ensure green after removal
            result2 = _run(["uv", "run", "tach", "check"])
            if "No such file" in result2.stderr or "Failed to spawn" in result2.stderr:
                result2 = _run(["uv", "run", "--with", "tach", "tach", "check"])
            assert result2.returncode == 0, f"tach check should pass after removal: {result2.stdout} {result2.stderr}"


# ---------------------------------------------------------------------------
# 6.6 Makefile tach targets
# ---------------------------------------------------------------------------


class TestMakefileTach:
    """6.6 RED: Makefile must have tach + tach-external targets and .PHONY."""

    def test_makefile_has_tach_target(self) -> None:
        content = MAKEFILE.read_text()
        assert "tach:" in content, "Makefile missing tach: target"
        # must run both checks
        assert "tach check" in content
        assert "tach check-external" in content

    def test_makefile_tach_external_target(self) -> None:
        content = MAKEFILE.read_text()
        # optional tach-external target
        assert "tach-external" in content or "tach check-external" in content

    def test_phony_includes_tach(self) -> None:
        content = MAKEFILE.read_text()
        for line in content.splitlines():
            if line.strip().startswith(".PHONY"):
                assert "tach" in line, f".PHONY missing tach: {line}"
                return
        raise AssertionError("no .PHONY found")


# ---------------------------------------------------------------------------
# 6.7 ci.yml + prek.toml tach gates
# ---------------------------------------------------------------------------


class TestCITachGates:
    """6.7 RED: ci.yml quality job + prek.toml pre-push must run tach check (blocking)."""

    def test_ci_has_tach_check_steps(self) -> None:
        data = yaml.safe_load(CI_YML.read_text())
        jobs = data.get("jobs", {})
        # find job containing tach — qa-matrix
        found_check = False
        found_external = False
        text = CI_YML.read_text()
        assert "tach check" in text, "ci.yml missing tach check"
        assert "tach check-external" in text, "ci.yml missing tach check-external"
        for job in jobs.values():
            for step in job.get("steps", []) or []:
                run = step.get("run", "") or ""
                if "tach check" in run and "check-external" not in run:
                    found_check = True
                    assert step.get("continue-on-error") is not True, "tach check must be blocking"
                if "tach check-external" in run:
                    found_external = True
                    assert step.get("continue-on-error") is not True, "tach check-external must be blocking"
        assert found_check, "tach check step not found in ci.yml jobs"
        assert found_external, "tach check-external step not found in ci.yml jobs"

    def test_prek_has_tach_prepush(self) -> None:
        content = PREK_TOML.read_text()
        assert "tach check" in content
        assert "tach check-external" in content
        # pre-push stage
        assert "pre-push" in content


# ---------------------------------------------------------------------------
# 6.8 make ci green — delegated to outer harness, but ensure basic ci targets exist
# ---------------------------------------------------------------------------


class TestMakeCiTargets:
    """6.8 sanity: ci chain exists and lints."""

    def test_ci_target_exists(self) -> None:
        content = MAKEFILE.read_text()
        assert "ci:" in content
        assert "lint" in content
        assert "type" in content
        assert "test" in content
        assert "cov" in content
