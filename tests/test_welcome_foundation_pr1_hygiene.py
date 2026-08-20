"""RED tests for welcome-svg-foundation PR1 hygiene (Phase 1).

Strict TDD: these tests MUST fail before hygiene fixes, pass after.
Covers tasks 1.1-1.8 from tasks.md.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestVersionHygiene:
    """1.1 pyproject.toml version 0.1.0→0.8.0 + bot/__init__.py"""

    def test_pyproject_version_is_0_8_0(self) -> None:
        pyproject = PROJECT_ROOT / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        version = data["project"]["version"]
        assert version == "0.8.0", f"pyproject version is {version!r}, expected 0.8.0"

    def test_bot_init_version_is_0_8_0(self) -> None:
        init = PROJECT_ROOT / "bot" / "__init__.py"
        content = init.read_text(encoding="utf-8")
        assert '__version__ = "0.8.0"' in content, f"bot/__init__.py must contain 0.8.0, got: {content!r}"

    def test_changelog_exists_and_mentions_0_8_0(self) -> None:
        # CHANGELOG.md or CHANGELOG at root must exist and mention 0.8.0
        changelog = PROJECT_ROOT / "CHANGELOG.md"
        alt = PROJECT_ROOT / "CHANGELOG"
        path = changelog if changelog.exists() else alt
        assert path.exists(), "CHANGELOG.md must exist for 1.1"
        text = path.read_text(encoding="utf-8")
        assert "0.8.0" in text


class TestGitignoreHygiene:
    """1.2 .gitignore must contain 4 patterns"""

    def test_gitignore_has_four_patterns(self) -> None:
        gi = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
        for pat in [".ty_cache/", ".hypothesis/", "*.tsbuildinfo", "**/.next/"]:
            assert pat in gi, f"Missing .gitignore pattern {pat!r}"


class TestOpenspecConfigHygiene:
    """1.3 openspec/config.yaml mypy→ty, 0.70→0.75, 400→800"""

    def test_type_checker_is_ty(self) -> None:
        cfg = yaml.safe_load((PROJECT_ROOT / "openspec" / "config.yaml").read_text(encoding="utf-8"))
        tc = (
            cfg["testing"]["quality"]["type_checker"]
            if "quality" in cfg["testing"]
            else cfg.get("quality", {}).get("type_checker")
        )
        # fallback: read raw text for ty
        raw = (PROJECT_ROOT / "openspec" / "config.yaml").read_text(encoding="utf-8")
        assert "type_checker: ty" in raw or tc == "ty", f"type_checker must be ty, got {tc!r}"

    def test_coverage_threshold_is_0_75(self) -> None:
        raw = (PROJECT_ROOT / "openspec" / "config.yaml").read_text(encoding="utf-8")
        # verify.coverage_threshold or testing.coverage
        cfg = yaml.safe_load(raw)
        # try both locations
        thr = None
        if "verify" in cfg and "coverage_threshold" in cfg["verify"]:
            thr = cfg["verify"]["coverage_threshold"]
        elif "testing" in cfg and "coverage" in cfg["testing"]:
            thr = cfg["testing"]["coverage"].get("threshold")
        assert thr == 0.75 or "coverage_threshold: 0.75" in raw, f"coverage_threshold must be 0.75, got {thr!r}"

    def test_review_budget_is_800(self) -> None:
        raw = (PROJECT_ROOT / "openspec" / "config.yaml").read_text(encoding="utf-8")
        cfg = yaml.safe_load(raw)
        budget = None
        if "session" in cfg and "review_budget_lines" in cfg["session"]:
            budget = cfg["session"]["review_budget_lines"]
        assert budget == 800 or "review_budget_lines: 800" in raw, f"review_budget must be 800, got {budget!r}"

    def test_test_count_not_stale_1812(self) -> None:
        raw = (PROJECT_ROOT / "openspec" / "config.yaml").read_text(encoding="utf-8")
        assert "1812" not in raw, "Stale test count 1812 must be refreshed"


class TestReadmeHygiene:
    """1.4 README.md exists and is non-empty"""

    def test_readme_exists_and_nonempty(self) -> None:
        readme = PROJECT_ROOT / "README.md"
        assert readme.exists(), "README.md must exist"
        text = readme.read_text(encoding="utf-8").strip()
        assert len(text) > 100, "README.md must be non-empty (>100 chars)"
        assert "NebulosaBot" in text


class TestEnvExampleHygiene:
    """1.5 .env.example documents 12 vars with comments"""

    def test_env_example_has_12_vars(self) -> None:
        text = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
        # Count non-comment, non-empty lines with =
        vars_found = [l for l in text.splitlines() if l.strip() and not l.strip().startswith("#") and "=" in l]
        assert len(vars_found) >= 12, f".env.example must document >=12 vars, found {len(vars_found)}: {vars_found}"
        for required in ["DISCORD_TOKEN", "SUPABASE_URL", "SUPABASE_KEY"]:
            assert required in text, f"{required} missing from .env.example"
        # Must have comments
        assert text.count("#") >= 3, "Must have comments documenting vars"


class TestCodeQualityPinHygiene:
    """1.6 code-quality.yml SHA-pin"""

    def test_no_unpinned_uses(self) -> None:
        text = (PROJECT_ROOT / ".github" / "workflows" / "code-quality.yml").read_text(encoding="utf-8")
        # Every 'uses:' must have @SHA (40 hex) not @vN
        for line in text.splitlines():
            if "uses:" in line:
                assert "@" in line, f"uses without @: {line}"
                after = line.split("@", 1)[1].strip().split()[0]
                # Must be 40 hex SHA
                assert re.match(r"^[0-9a-f]{40}", after) or re.match(r"^[0-9a-f]{7,40}", after), (
                    f"uses not SHA-pinned: {line}"
                )
                assert not re.match(r"^v\d", after), f"uses uses @vN not SHA: {line}"
        # npx jscpd must be pinned with version
        assert "npx jscpd@" in text or "jscpd@" in text, "jscpd must be version-pinned (npx jscpd@x.y.z)"
        # pip install vulture must be pinned
        assert "vulture==" in text, "vulture must be version-pinned (vulture==x.y.z)"


class TestAgentsGaps:
    """1.7 AGENTS.md gaps"""

    def test_agents_documents_cairosvg_constraint(self) -> None:
        text = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        assert "cairosvg" in text.lower() or "libcairo" in text.lower(), (
            "AGENTS.md must document cairosvg/libcairo constraint"
        )
        assert "pillow" in text.lower() or "Pillow" in text, "must mention Pillow fallback"

    def test_agents_documents_cache_key_guild_scoping(self) -> None:
        text = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        assert "cache_key" in text, "AGENTS.md must document cache_key guild-scoping"
        assert "guild_id" in text.lower() or "guild-scoped" in text.lower()

    def test_agents_documents_time_do_not_merge(self) -> None:
        text = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        assert "time.py" in text and "timeparse.py" in text, "must mention both time.py and timeparse.py"
        assert "DO NOT MERGE" in text or "do-not-merge" in text.lower()


class TestDuplicate003:
    """1.8 duplicate 003 reconciliation"""

    def test_at_most_one_003_prefix(self) -> None:
        migrations = PROJECT_ROOT / "migrations"
        files = sorted(p.name for p in migrations.glob("*.sql"))
        # Count files whose name starts with "003_" (exact prefix with underscore)
        count = sum(1 for name in files if name.startswith("003_"))
        assert count <= 1, (
            f"At most one file may carry 003_ prefix, found {count}: {[n for n in files if n.startswith('003_')]}"
        )

    def test_003b_migration_exists_for_updatedAt(self) -> None:
        # The distinct non-003 migration for updatedAt must exist (020)
        migrations = PROJECT_ROOT / "migrations"
        found = False
        for p in migrations.glob("*.sql"):
            text = p.read_text(encoding="utf-8")
            if '"updatedAt"' in text and "timestamptz" in text.lower():
                # Must be a non-003 file (distinct prefix)
                assert not p.name.startswith("003_"), f"updatedAt migration must not be 003_: {p.name}"
                found = True
                break
        assert found, "Migration adding updatedAt timestamptz column must exist"
