# Changelog

All notable changes to NebulosaBot are documented here.

## Cycle 5 — Quality Zero (unreleased; v1.0 readiness)

> Unbracketed by design: version headings are pinned to pyproject by
> `TestVersionHygiene`; retitle this section `## [1.0.0] - <date>` when cutting
> the release.

### Added
- Fatal `ty` type gate (`error-on-warning = true`); tests/ diagnostics 495 → 0.
- InfractionService mute/kick/ban persistence with caller-side single audit.
- CDC realtime for `member` / `economy_config`: publication + `updatedAt` columns,
  subscription, incremental poll, watchdog counter, echo suppression on RPC mutators.
- LoggingService i18n: moderation/voice events localized ES/EN with AST-level
  anti-drift guard.
- Resource-log heartbeat loop in CoreCog.

### Changed
- Slash-only command surface: prefix invocation inert (`_noop_prefix` returns `[]`);
  `,` reserved exclusively for the ticket close-timer listener.
- Global error handler delivers one channel embed via `t()`; DM-first branch removed.
- GreetingService is protocol-only (ImageService deleted; renderer contract enforced).
- Economy config reads are cache-first with TTL + invalidation; transcript HTML built
  via `asyncio.to_thread`; greeting dispatch raid-guarded; `,`-timer debounced 15 s.
- AGENTS.md v3: slash-only policy, PLC0415 exception policy, i18n/brand-token rules.
- Migrations resynced and pushed: 025 DROP legacy backup table, 026 realtime
  publication (26/26 local = remote).

### Removed
- `ImageService` shim and its test files (~780 lines).
- ~4,000 lines of duplicate/theater test code across consolidation batches while
  preserving behavioral twins.

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
