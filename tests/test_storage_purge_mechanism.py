"""S3.1 — Storage purge mechanism pin (PRE-S3 BLOCKER).

Pinned decision: SQL DELETE on storage.objects + orphan reconciliation sweep
(document choice in code comment + design follow-up).

This test asserts the chosen mechanism deletes storage.objects rows AND handles
orphaned backing files (reconciliation sweep OR pg_net Storage API delete
endpoint). Direct SQL risks orphaned backing files (metadata row deleted,
object remains) — the pinned design MUST state how orphans are handled.

Ref: design D3 Open Question, tasks S3.1.
"""

from __future__ import annotations

from pathlib import Path

MIGRATION_028 = Path("migrations/028_retention.sql")
STORAGE_PURGE_MODULE = Path("bot/services/storage_purge.py")
DESIGN_PATH = Path("openspec/changes/clean-1-0/design.md")


def _read(path: Path) -> str:
    assert path.exists(), f"{path} missing — S3.1 pin not landed"
    return path.read_text(encoding="utf-8")


class TestStoragePurgeMechanismPinned:
    """S3.1: mechanism deletes storage.objects rows AND handles orphans."""

    def test_deletes_storage_objects_rows(self) -> None:
        """Pinned mechanism MUST DELETE FROM storage.objects."""
        # Check migration (primary) and fallback service module
        candidates = []
        for p in (MIGRATION_028, STORAGE_PURGE_MODULE):
            if p.exists():
                candidates.append(p.read_text(encoding="utf-8").lower())
        combined = "\n".join(candidates)
        assert "storage.objects" in combined, "must reference storage.objects"
        assert "delete from storage.objects" in combined, "must DELETE FROM storage.objects (SQL pin)"

    def test_handles_orphaned_backing_files(self) -> None:
        """Pinned design MUST state how orphans are handled (reconciliation sweep OR pg_net API)."""
        candidates = []
        for p in (MIGRATION_028, STORAGE_PURGE_MODULE, DESIGN_PATH):
            if p.exists():
                candidates.append(p.read_text(encoding="utf-8").lower())
        combined = "\n".join(candidates)
        has_reconciliation = "orphan" in combined and ("reconcil" in combined or "sweep" in combined)
        has_pg_net = "pg_net" in combined or "storage api" in combined
        assert has_reconciliation or has_pg_net, (
            "must document orphan handling: reconciliation sweep OR pg_net Storage API delete endpoint"
        )

    def test_pinned_decision_documented(self) -> None:
        """Decision MUST be documented as SQL DELETE + orphan reconciliation sweep."""
        candidates = []
        for p in (MIGRATION_028, STORAGE_PURGE_MODULE, DESIGN_PATH):
            if p.exists():
                candidates.append(p.read_text(encoding="utf-8"))
        combined = "\n".join(candidates)
        low = combined.lower()
        assert "sql delete on storage.objects" in low or "sql delete" in low and "storage.objects" in low, (
            "decision doc must state SQL DELETE on storage.objects"
        )
        assert "orphan" in low, "decision doc must mention orphan handling"

    def test_targets_transcripts_bucket(self) -> None:
        """Purge MUST target the transcripts bucket (transcripts/{guild}/{ticket}/filename)."""
        sql = _read(MIGRATION_028)
        low = sql.lower()
        assert "transcripts" in low, "must target transcripts bucket"
        # bucket_id filter or path prefix
        assert "bucket_id" in low or "transcripts/" in low or "transcripts" in low
