"""RED for PR2 2.9 parse_duration_optional (strict TDD)."""

from bot.utils import time as time_module


def test_parse_duration_optional_exists():
    assert hasattr(time_module, "parse_duration_optional"), "parse_duration_optional must exist in bot/utils/time.py"


def test_parse_duration_optional_valid():
    from bot.utils.time import parse_duration_optional

    assert parse_duration_optional("1h") == 3600
    assert parse_duration_optional("30m") == 1800
    assert parse_duration_optional("7d") == 604800
    assert parse_duration_optional("1h30m") == 5400


def test_parse_duration_optional_invalid_returns_none():
    from bot.utils.time import parse_duration_optional

    assert parse_duration_optional("notaduration") is None
    assert parse_duration_optional("") is None
    assert parse_duration_optional("   ") is None
    assert parse_duration_optional("notaduration") != 3600
    assert parse_duration_optional("") != 3600


def test_parse_duration_optional_docstring_mentions_timeparse():
    """Docstring must note timeparse.py is a separate domain."""
    from bot.utils.time import parse_duration_optional

    doc = parse_duration_optional.__doc__ or ""
    # Accept either mention of timeparse or DO NOT MERGE
    assert "timeparse" in doc.lower() or "do not merge" in doc.lower(), (
        "docstring must note timeparse.py separate domain"
    )
