# Changelog

All notable changes to NebulosaBot are documented here.

## [0.9.0] - 2026-08-23

### Added
- Sentinel permission matrix gates with escalation chain.
- jscpd duplication ratchet gate (`scripts/jscpd_check.py`).
- betterleaks staged-scan pre-commit hook; `requirements.txt` regenerated from `uv.lock`.

### Changed
- AGENTS.md code review rules v3 (rule-cited, diff-scoped blocking).
- Toolchain hardening: PEP 735 dev dependency group, exact `ty` pin, `uv audit` replaces pip-audit.

### Fixed
- Version surfaces aligned to pyproject source of truth (`bot/__init__.py`, this changelog).

## [0.8.0] - 2026-08-19

### Added
- Hygiene baseline for welcome-svg-foundation Cycle 1 (version sync, gitignore, config, README, .env docs, SHA-pinned CI).
- Preparation for `greeting_config.updatedAt` (additive nullable timestamptz) and incremental Realtime poll.

### Changed
- Version bump `0.1.0` → `0.8.0` to match `v0.8.0-qa-modernization` release state.

### Fixed
- `openspec/config.yaml` now declares `ty` (was `mypy`), coverage `0.75` (was `0.70`), review budget `800` (was `400`).
- `.gitignore` now covers `.ty_cache/`, `.hypothesis/`, `*.tsbuildinfo`, `**/.next/`.
- `.env.example` documents Discord, Supabase, and feature vars.

## [0.1.0] - Initial
- Initial project scaffold.
