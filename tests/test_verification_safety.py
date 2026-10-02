"""Regression tests for verification safety and checkout isolation.

Ensures:
1. Vitest config sets envDir: false to block loading real .env.local in tests.
2. Tach boundary tests do not mutate live bot/models/ticket.py.
3. Prek hook behavior tests do not mutate checkout or write to live tests/ directory.
4. docs/development.md documents verification boundaries.
"""

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VITEST_CONFIG = PROJECT_ROOT / "dashboard" / "vitest.config.ts"
DEVELOPMENT_DOC = PROJECT_ROOT / "docs" / "development.md"
PREK_TEST = PROJECT_ROOT / "tests" / "test_prek_config.py"
TACH_TEST = PROJECT_ROOT / "tests" / "test_pr6_tach_boundaries.py"
LIVE_TICKET_PY = PROJECT_ROOT / "bot" / "models" / "ticket.py"


class TestVerificationSafetyBoundaries:
    def test_vitest_config_has_envdir_false(self) -> None:
        """Vitest config must declare envDir: false to disable .env file autoloading."""
        assert VITEST_CONFIG.exists(), "dashboard/vitest.config.ts must exist"
        content = VITEST_CONFIG.read_text(encoding="utf-8")
        assert re.search(r"\benvDir:\s*false\b", content), (
            "vitest.config.ts must explicitly configure 'envDir: false' to prevent loading .env.local"
        )

    def test_development_guide_exists_and_documents_boundaries(self) -> None:
        """docs/development.md must exist and document verification safety boundaries."""
        assert DEVELOPMENT_DOC.exists(), "docs/development.md must exist"
        content = DEVELOPMENT_DOC.read_text(encoding="utf-8")
        assert "Verification" in content or "verification" in content
        assert "envDir" in content or ".env.local" in content
        assert "prek" in content
        assert "tach" in content

    def test_tach_test_does_not_mutate_live_source(self) -> None:
        """tests/test_pr6_tach_boundaries.py must not overwrite bot/models/ticket.py directly."""
        content = TACH_TEST.read_text(encoding="utf-8")
        # Ensure it uses tmp_path or fixture rather than directly writing to the live ticket.py path
        assert "tmp_path" in content, (
            "test_pr6_tach_boundaries.py must use tmp_path fixture for architectural fault injection"
        )
        assert "ticket_py.write_text(injected)" not in content, (
            "test_pr6_tach_boundaries.py must not directly write injected imports to live ticket.py"
        )

    def test_prek_test_does_not_create_live_scratch_files(self) -> None:
        """tests/test_prek_config.py must not write scratch files to live tests/ directory."""
        content = PREK_TEST.read_text(encoding="utf-8")
        assert 'PROJECT_ROOT / "tests" / "_tmp_prek_trailing_ws.py"' not in content, (
            "test_prek_config.py must not write scratch files to live repo tests/ directory"
        )
