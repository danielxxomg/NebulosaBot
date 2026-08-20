"""RED tests for welcome-svg-foundation PR1 Phase 2 DRY (2.1-2.5).

Strict TDD: must fail before DRY extracts, pass after.
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DASH_LIB = PROJECT_ROOT / "dashboard" / "lib" / "actions"
COGS = PROJECT_ROOT / "bot" / "cogs"
UTILS = PROJECT_ROOT / "bot" / "utils"


class TestGuardsExtract:
    """2.1 dashboard/lib/guards.ts single verifyGuildAdmin; 4 files import it."""

    def test_guards_file_exists(self) -> None:
        guards = PROJECT_ROOT / "dashboard" / "lib" / "guards.ts"
        # also accept verifyGuildAdmin.ts per design open question, but spec says guards.ts
        alt = PROJECT_ROOT / "dashboard" / "lib" / "verifyGuildAdmin.ts"
        assert guards.exists() or alt.exists(), "dashboard/lib/guards.ts (or verifyGuildAdmin.ts) must exist"

    def test_single_definition(self) -> None:
        # Find guards file
        guards = PROJECT_ROOT / "dashboard" / "lib" / "guards.ts"
        if not guards.exists():
            guards = PROJECT_ROOT / "dashboard" / "lib" / "verifyGuildAdmin.ts"
        content = guards.read_text(encoding="utf-8")
        count = len(
            re.findall(r"function\s+verifyGuildAdmin|const\s+verifyGuildAdmin|export\s+.*verifyGuildAdmin", content)
        )
        assert count >= 1, "guards must define verifyGuildAdmin"
        # Check 4 action files do NOT define their own
        for name in ["economy-actions.ts", "guild-actions.ts", "greeting-actions.ts", "ticket-actions.ts"]:
            p = DASH_LIB / name
            text = p.read_text(encoding="utf-8")
            # count local definitions: async function verifyGuildAdmin
            local = len(re.findall(r"async\s+function\s+verifyGuildAdmin", text))
            # If file imports, local must be 0
            if 'from "@/lib/guards"' in text or "from '@/lib/guards'" in text or "guards" in text:
                assert local == 0, f"{name} must not redefine verifyGuildAdmin, found {local}"
            else:
                # Before fix, this will fail because they do define it and don't import
                assert "guards" in text, f"{name} must import shared guard from guards"

    def test_action_files_import_guards(self) -> None:
        for name in ["economy-actions.ts", "guild-actions.ts", "greeting-actions.ts", "ticket-actions.ts"]:
            text = (DASH_LIB / name).read_text(encoding="utf-8")
            assert "guards" in text.lower() or "verifyGuildAdmin" in text, f"{name} must reference guards"
            # Must import
            assert "import" in text and "verifyGuildAdmin" in text

    def test_guards_parameterizes_error_string(self) -> None:
        guards = PROJECT_ROOT / "dashboard" / "lib" / "guards.ts"
        if not guards.exists():
            guards = PROJECT_ROOT / "dashboard" / "lib" / "verifyGuildAdmin.ts"
        text = guards.read_text(encoding="utf-8")
        # Must accept error string param or options
        assert "error" in text.lower() or "message" in text.lower(), "guard must parameterize error string"


class TestSelectStar:
    """2.2 select('*') x13 -> explicit columns in dashboard actions."""

    def test_no_select_star_in_actions(self) -> None:
        offenders = []
        for p in DASH_LIB.glob("*.ts"):
            text = p.read_text(encoding="utf-8")
            if 'select("*")' in text or "select('*')" in text:
                offenders.append(p.name)
        assert not offenders, f"select('*') found in dashboard actions: {offenders}. Use explicit column lists."

    def test_no_select_star_in_dashboard_app(self) -> None:
        # Also check app greeting/economy pages — ignore test helpers
        offenders = []
        for p in (PROJECT_ROOT / "dashboard").rglob("*.ts*"):
            if "node_modules" in str(p) or ".next" in str(p) or "__tests__" in str(p):
                continue
            text = p.read_text(encoding="utf-8")
            if 'select("*")' in text or "select('*')" in text:
                offenders.append(str(p.relative_to(PROJECT_ROOT)))
        assert not offenders, f"select('*') still present in dashboard: {offenders}"


class TestEmbedHelpers:
    """2.3 shared _err/_ok/_info in bot/utils/embeds.py; 4 cogs import."""

    def test_embeds_has_shared_helpers(self) -> None:
        text = (UTILS / "embeds.py").read_text(encoding="utf-8")
        # Must have helpers that wrap t() and error_embed/success_embed/info_embed
        assert "def cog_err" in text or "def _err" in text or "def localized" in text or "def err_" in text, (
            "embeds.py must define shared _err helper"
        )
        assert "def cog_ok" in text or "def _ok" in text, "embeds.py must define shared _ok helper"
        assert "def cog_info" in text or "def _info" in text, "embeds.py must define shared _info helper"

    def test_cogs_no_local_err_ok(self) -> None:
        # 4 cogs must not define local _err/_ok
        for name in [
            "ticket_admin_flow.py",
            "ticket_notes_flow.py",
            "ticket_integrity_flow.py",
            "ticket_lifecycle_flow.py",
        ]:
            text = (COGS / name).read_text(encoding="utf-8")
            # After fix, no local def _err
            has_local = "def _err" in text
            # Allow if they import
            imports_embeds = "from bot.utils.embeds import" in text and ("_err" in text or "cog_err" in text)
            assert not has_local or imports_embeds, f"{name} must not define local _err, must import from embeds.py"


class TestInfoBrandBypass:
    """2.4 INFO bypass fix."""

    def test_no_local_info_in_ticket_cogs(self) -> None:
        for name in ["ticket_admin_flow.py", "ticket_notes_flow.py"]:
            text = (COGS / name).read_text(encoding="utf-8")
            assert "INFO = discord.Color.from_str" not in text, f"{name} must not define local INFO"
            assert "5865F2" not in text, f"{name} must not contain hardcoded 5865F2"
            assert (
                "from bot.utils.brand import" in text or "from bot.utils import brand" in text or "brand.INFO" in text
            ), f"{name} must import brand.INFO"

    def test_brand_info_used(self) -> None:
        for name in ["ticket_admin_flow.py", "ticket_notes_flow.py"]:
            text = (COGS / name).read_text(encoding="utf-8")
            assert "INFO" in text, f"{name} must use INFO token"
            assert "brand" in text.lower(), f"{name} must import from brand"


class TestDoNotMergeDocstrings:
    """2.5 time.py/timeparse.py docstrings stating DO NOT MERGE."""

    def test_time_py_docstring(self) -> None:
        text = (UTILS / "time.py").read_text(encoding="utf-8")
        assert "timeparse" in text.lower(), "time.py must mention timeparse.py"
        assert "DO NOT MERGE" in text or "do not merge" in text.lower(), "time.py must state DO NOT MERGE"
        assert "separate" in text.lower() or "different domain" in text.lower()

    def test_timeparse_py_docstring(self) -> None:
        text = (UTILS / "timeparse.py").read_text(encoding="utf-8")
        assert "time.py" in text.lower(), "timeparse.py must mention time.py"
        assert "DO NOT MERGE" in text or "do not merge" in text.lower(), "timeparse.py must state DO NOT MERGE"
