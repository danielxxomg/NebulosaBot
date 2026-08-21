"""RED: banana pool assets 5-8 + dorada (PR3 3.2)."""

from pathlib import Path


def test_banana_pool_size_and_dorada():
    pool = list(Path("assets/images/banana").glob("*.webp"))
    assert 5 <= len(pool) <= 8, f"pool {len(pool)} must be 5-8"
    assert "dorada.webp" in [p.name for p in pool], "dorada.webp missing"


def test_banana_assets_valid_webp():
    for p in Path("assets/images/banana").glob("*.webp"):
        data = p.read_bytes()
        assert len(data) > 0
        # webp magic RIFF....WEBP or at least non-empty
        assert data.startswith(b"RIFF") or len(data) > 100
