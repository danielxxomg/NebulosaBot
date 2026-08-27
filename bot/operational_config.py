"""Typed operational config loader (restart-only, tomllib).

Precedence: built-in defaults ← config.toml ; .env never feeds operational settings.
Absent file → defaults ; malformed → TOMLDecodeError fail-fast ; unknown keys → WARNING ignored.
"""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LoggingSettings:
    level: str = "INFO"
    file: str = "logs/bot.log"


@dataclass(frozen=True)
class LimitSettings:
    rank_render_max_concurrent: int = 3
    backfill_concurrency: int = 50


@dataclass(frozen=True)
class TimeoutSettings:
    integrity_backoff_seconds: float = 1.0


@dataclass(frozen=True)
class RetentionSettings:
    tickets: int = 30
    infractions: int = 180
    crash: int = 30


@dataclass(frozen=True)
class FeatureFlags:
    retention_enabled: bool = True


@dataclass(frozen=True)
class OperationalConfig:
    logging: LoggingSettings = field(default_factory=LoggingSettings)
    limits: LimitSettings = field(default_factory=LimitSettings)
    timeouts: TimeoutSettings = field(default_factory=TimeoutSettings)
    retention: RetentionSettings = field(default_factory=RetentionSettings)
    flags: FeatureFlags = field(default_factory=FeatureFlags)


# ---- helpers ----

_KNOWN_TOP = {"logging", "limits", "timeouts", "retention", "features"}
_KNOWN_LOGGING = {"level", "file"}
_KNOWN_LIMITS = {"rank_render_max_concurrent", "backfill_concurrency"}
_KNOWN_TIMEOUTS = {"integrity_backoff_seconds"}
_KNOWN_RETENTION = {"tickets", "infractions", "crash"}
_KNOWN_FEATURES = {"retention_enabled"}


def _warn_unknown(where: str, key: str) -> None:
    logger.warning("Unknown config key %r in [%s] — ignored", key, where)


def _coerce_int(value: object, key: str, section: str, default: int) -> int:
    if isinstance(value, bool):
        _warn_unknown(section, f"{key} (expected int, got bool)")
        return default
    if isinstance(value, int):
        return value
    _warn_unknown(section, f"{key} (expected int, got {type(value).__name__})")
    return default


def _coerce_float(value: object, key: str, section: str, default: float) -> float:
    if isinstance(value, bool):
        _warn_unknown(section, f"{key} (expected float, got bool)")
        return default
    if isinstance(value, (int, float)):
        return float(value)
    _warn_unknown(section, f"{key} (expected float, got {type(value).__name__})")
    return default


def _coerce_str(value: object, key: str, section: str, default: str) -> str:
    if isinstance(value, str):
        return value
    _warn_unknown(section, f"{key} (expected str, got {type(value).__name__})")
    return default


def _coerce_bool(value: object, key: str, section: str, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    _warn_unknown(section, f"{key} (expected bool, got {type(value).__name__})")
    return default


def load_operational_config(path: Path | str | None = None) -> OperationalConfig:  # noqa: C901,RUF001 -- five sections x coercion branches, bounded by D4
    """Load operational config from TOML file or return defaults.

    Args:
        path: Path to config.toml. If None, uses ``config.toml`` in the
            current working directory. Absent file → defaults (env-only boot).

    Returns:
        Frozen :class:`OperationalConfig` with built-in defaults ← TOML overlay.

    Raises:
        tomllib.TOMLDecodeError: if the file is syntactically invalid (fail-fast).
    """
    cfg_path = Path(path) if path is not None else Path("config.toml")

    if not cfg_path.exists():
        return OperationalConfig()

    # May raise TOMLDecodeError — fail-fast per spec
    with cfg_path.open("rb") as fh:
        data: dict[str, object] = tomllib.load(fh)

    # Top-level unknown keys → WARNING
    for key in list(data.keys()):
        if key not in _KNOWN_TOP:
            logger.warning("Unknown config section [%s] — ignored", key)

    # Start from defaults
    logging_level = LoggingSettings.level
    logging_file = LoggingSettings.file
    rank_render = LimitSettings.rank_render_max_concurrent
    backfill = LimitSettings.backfill_concurrency
    backoff = TimeoutSettings.integrity_backoff_seconds
    tickets = RetentionSettings.tickets
    infractions = RetentionSettings.infractions
    crash = RetentionSettings.crash
    retention_enabled = FeatureFlags.retention_enabled

    raw_logging = data.get("logging")
    if isinstance(raw_logging, dict):
        for k, v in raw_logging.items():
            if k not in _KNOWN_LOGGING:
                _warn_unknown("logging", k)
                continue
            if k == "level":
                logging_level = _coerce_str(v, k, "logging", logging_level)
            elif k == "file":
                logging_file = _coerce_str(v, k, "logging", logging_file)
    elif raw_logging is not None:
        logger.warning("Unknown config value for [logging] — expected table, ignored")

    raw_limits = data.get("limits")
    if isinstance(raw_limits, dict):
        for k, v in raw_limits.items():
            if k not in _KNOWN_LIMITS:
                _warn_unknown("limits", k)
                continue
            if k == "rank_render_max_concurrent":
                rank_render = _coerce_int(v, k, "limits", rank_render)
            elif k == "backfill_concurrency":
                backfill = _coerce_int(v, k, "limits", backfill)
    elif raw_limits is not None:
        logger.warning("Unknown config value for [limits] — expected table, ignored")

    raw_timeouts = data.get("timeouts")
    if isinstance(raw_timeouts, dict):
        for k, v in raw_timeouts.items():
            if k not in _KNOWN_TIMEOUTS:
                _warn_unknown("timeouts", k)
                continue
            if k == "integrity_backoff_seconds":
                backoff = _coerce_float(v, k, "timeouts", backoff)
    elif raw_timeouts is not None:
        logger.warning("Unknown config value for [timeouts] — expected table, ignored")

    raw_retention = data.get("retention")
    if isinstance(raw_retention, dict):
        for k, v in raw_retention.items():
            if k not in _KNOWN_RETENTION:
                _warn_unknown("retention", k)
                continue
            if k == "tickets":
                tickets = _coerce_int(v, k, "retention", tickets)
            elif k == "infractions":
                infractions = _coerce_int(v, k, "retention", infractions)
            elif k == "crash":
                crash = _coerce_int(v, k, "retention", crash)
    elif raw_retention is not None:
        logger.warning("Unknown config value for [retention] — expected table, ignored")

    raw_features = data.get("features")
    if isinstance(raw_features, dict):
        for k, v in raw_features.items():
            if k not in _KNOWN_FEATURES:
                _warn_unknown("features", k)
                continue
            if k == "retention_enabled":
                retention_enabled = _coerce_bool(v, k, "features", retention_enabled)
    elif raw_features is not None:
        logger.warning("Unknown config value for [features] — expected table, ignored")

    return OperationalConfig(
        logging=LoggingSettings(level=logging_level, file=logging_file),
        limits=LimitSettings(
            rank_render_max_concurrent=rank_render,
            backfill_concurrency=backfill,
        ),
        timeouts=TimeoutSettings(integrity_backoff_seconds=backoff),
        retention=RetentionSettings(tickets=tickets, infractions=infractions, crash=crash),
        flags=FeatureFlags(retention_enabled=retention_enabled),
    )
