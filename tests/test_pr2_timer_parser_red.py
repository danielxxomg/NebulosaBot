"""RED for PR2 2.1 parse_duration_strict + 2.3 format_remaining (strict TDD)."""

from bot.utils import time as time_module


def test_parse_duration_strict_exists():
    assert hasattr(time_module, "parse_duration_strict"), "parse_duration_strict must exist in bot/utils/time.py"


def test_parse_duration_strict_12h():
    from bot.utils.time import parse_duration_strict

    assert parse_duration_strict(",12h") == 43200


def test_parse_duration_strict_compound():
    from bot.utils.time import parse_duration_strict

    assert parse_duration_strict(",1d12h") == 129600


def test_parse_duration_strict_w_y():
    from bot.utils.time import parse_duration_strict

    assert parse_duration_strict(",1w") == 604800
    assert parse_duration_strict(",1y") == 31536000


def test_parse_duration_strict_space_separated_sum():
    from bot.utils.time import parse_duration_strict

    # 2h=7200 4h=14400 6h=21600 10h=36000 1d=86400 2d=172800 total=338400
    assert parse_duration_strict(",2h 4h 6h 10h 1d 2d") == 338400


def test_parse_duration_strict_failures_return_none():
    from bot.utils.time import parse_duration_strict

    assert parse_duration_strict(",hola") is None
    assert parse_duration_strict(",") is None
    assert parse_duration_strict("12") is None
    assert parse_duration_strict(",12") is None  # bare number no unit -> None
    assert parse_duration_strict(",1x") is None
    # Must NOT return 3600 fallback
    assert parse_duration_strict(",hola") != 3600


def test_parse_duration_strict_case_insensitive():
    from bot.utils.time import parse_duration_strict

    assert parse_duration_strict(",12H") == 43200


def test_format_remaining_exists_and_localized():
    from bot.utils.time import format_remaining

    # guild_id None -> fallback to es
    assert format_remaining(43200) in ("12h", "12 h", "12 horas")
    # explicit guild_id es/en both produce 12h-style
    assert "12" in format_remaining(43200, guild_id="123")


def test_time_vs_timeparse_docstrings_separate():
    import pathlib

    time_py = pathlib.Path("bot/utils/time.py").read_text()
    timeparse_py = pathlib.Path("bot/utils/timeparse.py").read_text()
    assert "timeparse" in time_py.lower() and "DO NOT MERGE" in time_py
    assert "time.py" in timeparse_py and "DO NOT MERGE" in timeparse_py
    # no re-export facade: time.py must not import timeparse's _to_datetime as alias
    assert "_to_datetime" not in time_py
