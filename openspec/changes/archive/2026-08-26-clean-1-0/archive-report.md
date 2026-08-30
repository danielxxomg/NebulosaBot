# Archive Report: clean-1.0 — Everything Clean Before v1.0.0

**Change**: `clean-1-0`
**Archived**: 2026-08-26
**Archived to**: `openspec/changes/archive/2026-08-26-clean-1-0/`
**Artifact store**: openspec (filesystem) + Engram mirror
**Evidence revision**: `fa7dcea` (all apply up to 48 commits ahead of origin/master)
**Verify report**: `openspec/changes/archive/2026-08-26-clean-1-0/verify-report.md` — authoritative, `pass_with_warnings`

## Final-State Authority

Per `sdd-archive` contract, final numbers are carried from the highest-ranked source:

1. **Persisted tasks artifact** — 77/77 checked (Task Completion Gate)
2. **Orchestrator final-state facts** — "all apply up to fa7dcea, verify-report authoritative. Forward outranks stale snapshots."
3. **verify-report / apply-progress** — intermediate snapshots, lowest rank

No contradictions to record; orchestrator facts corroborated by `verify-report` (pass_with_warnings, 0 critical) and `tasks.md` (all checked). No CRITICAL verification issues; archive proceeds under strict-vs-OpenSpec policy (CRITICAL would block, none present).

## Verification Summary

| Field | Value |
|-------|-------|
| Verdict | PASS WITH WARNINGS |
| Blockers | 0 |
| Critical findings | 0 |
| Requirements | 35/35 |
| Scenarios | 93/93 |
| Tests passed | 271 targeted (full suite 849+ passing, 271 hash `sha256:9e5a45e124a49fc51dbb5a66e27ce9d3272f82b23081613d8ffd8db7981a5917`) |
| Build | `uv run ruff check bot` — All checks passed (hash `sha256:1fa6c0d7ccd08299d8b55aab4b3138cca534cd6b8c2a7e647ed16bce3fee4b37`) |
| Coverage | Gate `80` via `pyproject --cov-fail-under=80`; capture disabled `--no-cov` for speed (CI enforces) |
| Type check | `ty` 80 diagnostics in `tests/` only; `bot/**` clean under preview ruleset |
| Branch | `master` @ `fa7dcea` (style: ruff format S6B ocio tests) |

All 9 stacked PRs (S0→S1→S2a→S2b→S3→S4→S5→S6A→S6B) verified. Comma-timer invariant (`TicketsCog.on_message` `,` close-timer) untouched — `tests/test_comma_timer_invariant.py` green. Zero-hybrid invariant held — AST scan 0 `hybrid_command`/`hybrid_group` in `bot/cogs/**`.

## Task Completion

| Field | Value |
|-------|-------|
| Tasks total | 77 |
| Tasks complete | 77 |
| Tasks incomplete | 0 |
| Unchecked boxes | 0 (`grep "^\- \[ \]"` 0) |

All implementation tasks marked `[x]` in persisted `tasks.md`. No stale checkboxes; no exceptional reconciliation required.

## Specs Synced

13 delta specs synced into `openspec/specs/` — 3 new domains via mechanical `cp` + `diff -r` (empty), 10 merges via spec-aware replacement.

| Domain | Action | Details |
|--------|--------|---------|
| **data-retention** | **Created** | NEW domain — 5 requirements (Ticket retention purge, Infraction retention, Tempban serialization, Crash report scope+TTL, Index hygiene), 11 scenarios |
| **operational-config** | **Created** | NEW domain — 3 requirements (Typed TOML loader, RotatingFileHandler, Token never logged), 8 scenarios |
| **setup-panel** | **Created** | NEW domain — 5 requirements (Persistent non-ephemeral panel, Module navigation, Authorization without new matrix key, Guided editors only, Internationalization), 12 scenarios |
| **bot-core** | Updated | 2 MODIFIED: Global error handler (added CheckFailure/MissingPermissions ephemeral localized branches, 2 new scenarios); Slash-only command surface (ZERO hybrid declarations remain, replaced comma-inert-outside scenario, 1 new scenario) |
| **cache-layer** | Updated | 2 ADDED: Eviction on guild remove (3 scenarios) + Documentation matches CDC reality (3 scenarios) |
| **core-commands** | Updated | 1 REMOVED: Sync command (Reason: manual /sync orphaned, Migration: tree.sync in setup_hook, restart to force re-sync) |
| **ephemeral-standard** | Updated | 2 MODIFIED: Slash-only error visibility (added CheckFailure denial ephemeral on permanent command, 1 scenario); Fun commands permanent standard (removed ocio ephemeral exception, made /dice+/8ball+/banana permanent, added 2 scenarios) |
| **ocio-commands** | Updated | 4 MODIFIED: Dice command (RENAMED /dados→/dice with `name_localizations` es:dados, 1 new scenario), Banana command (ephemeral→PERMANENT flip, 2 modified + 1 added scenario), 8ball command (hybrid→pure app_commands, ephemeral→PERMANENT, 4 scenarios rewritten), Ocio commands cooldown and handler (updated to `@app_commands.checks.cooldown` + /dice rename, 2 scenarios) — preserved OcioService service layer requirement |
| **permission-model** | Updated | 1 ADDED: Setup surface reuses existing matrix keys — no new key (4 scenarios, PERMISSIONS stays 7) |
| **setup-wizard** | Updated | 1 MODIFIED (Setup command: hybrid→pure app, zero params, 1 new scenario) + 2 REMOVED (Required parameter ticket_category, Optional parameters — moved to setup-panel Tickets module) |
| **ticket-service** | Updated | 1 ADDED: Zombie auto-close writes an audit entry (3 scenarios, action=zombie_autoclose, actorId=system, best-effort WARNING) |
| **transcript-service** | Updated | 2 ADDED: Triple-path transcript delivery (5 scenarios, DM+private Storage+log channel, best-effort independent, PATH semantics) + Log-channel-missing behavior preserved (1 scenario) |
| **welcome-goodbye** | Updated | 1 ADDED (Setup-module configuration parity and preview, 3 scenarios) + 1 MODIFIED (Localized greeting card text: removed Test-commands scenario, now caller-supplied t() only) + 2 REMOVED (Welcome config command group, Goodbye config command group — replaced by /setup modules) |

### Source of Truth Updated

New domains:
- `openspec/specs/data-retention/spec.md` (mechanical copy, identical to delta, 99 lines)
- `openspec/specs/operational-config/spec.md` (mechanical copy, 67 lines)
- `openspec/specs/setup-panel/spec.md` (mechanical copy, 104 lines)

Updated domains:
- `openspec/specs/bot-core/spec.md`
- `openspec/specs/cache-layer/spec.md`
- `openspec/specs/core-commands/spec.md`
- `openspec/specs/ephemeral-standard/spec.md`
- `openspec/specs/ocio-commands/spec.md`
- `openspec/specs/permission-model/spec.md`
- `openspec/specs/setup-wizard/spec.md`
- `openspec/specs/ticket-service/spec.md`
- `openspec/specs/transcript-service/spec.md`
- `openspec/specs/welcome-goodbye/spec.md`

All merges preserved non-delta requirements (e.g., bot-core Bot lifecycle/Cog loading, cache-layer Per-guild TTL/Cache operations, core-commands Ping/Status/Help, ephemeral-standard Command visibility classification/Admin/Mod/Personal standards, etc.). No destructive truncation.

## Archive Contents

- proposal.md ✅
- design.md ✅ (D1–D7 decisions, 9 stacked PRs)
- specs/ ✅ (13 delta specs, each domain)
- tasks.md ✅ (77/77 tasks complete)
- verify-report.md ✅ (pass_with_warnings, 35/35 requirements, 93/93 scenarios)

Active `openspec/changes/clean-1-0/` removed; archived at `openspec/changes/archive/2026-08-26-clean-1-0/`.

## Mechanical Copy Verification (MANDATORY readback)

All copies verified byte-identical via shell `diff -r` (empty output = PASS). Model Read→Write was NEVER used for copy; only `cp`/`mv`/`git mv`.

### New spec mechanical copies

```text
--- diff data-retention delta vs temp (should be empty) ---
(empty)

--- diff operational-config ---
(empty)

--- diff setup-panel ---
(empty)

Final verification per domain:
== data-retention ==
identical
== operational-config ==
identical
== setup-panel ==
identical
```

### Archive folder mechanical move

```text
snapshot_root=/tmp/sdd-archive.na1MNh
attempt git mv openspec/changes/clean-1-0 -> openspec/changes/archive/2026-08-26-clean-1-0
git mv succeeded
source gone, diff snapshot vs destination
diff empty - PASS
```

Verbatim `diff -r "$snapshot_root/source" "$destination"` produced no output (empty diff) — the only passing evidence per Mechanical Copy Contract.

## Archive Verification Checklist

- [x] Main specs updated correctly (3 created + 10 merged, diff-verified)
- [x] Change folder moved to archive `openspec/changes/archive/2026-08-26-clean-1-0/`
- [x] Archive contains all artifacts (proposal, specs/13, design, tasks 77/77, verify-report 35/35)
- [x] Archived `tasks.md` has no unchecked implementation tasks
- [x] Active changes directory no longer has this change
- [x] Verbatim `diff -r` readback included and empty (no differences)

## Warnings & Gaps (non-blocking, intentional-with-warnings)

No CRITICAL. verify-report warnings are doc/test-harness hygiene only, not spec deviations:

1. **Docstring hybrid examples** — `bot/utils/checks.py:229,361` still show literal `@commands.hybrid_command(name="sync")` as usage documentation. AST scan confirms 0 real hybrid registrations in `bot/cogs/**`; scoped `tests/test_zero_hybrid_guard.py` correctly scopes to decorator registrations (not docstring substring). GGA MUST cite decorator registration, not substring. Suggestion: normalize examples to `@app_commands.command`.

2. **ty diagnostics** — `uv run ty check` emits ~80 diagnostics, all in `tests/` (`.callback` on `Group` union, unused `type: ignore`). `bot/**` clean under `[tool.ty.overrides]` preview ruleset. Test-harness debt, non-blocking.

3. **Coverage capture disabled** — verify capture used `--no-cov` to hit 271 targeted fast; full `uv run pytest` with default `--cov` addopts enforces `80` via pyproject; CI enforces orthogonally. Fresh full run was 849+ passing.

Suggestions (non-blocking):
- Add permanent AST-level repo-wide hybrid guard (not substring grep) alongside scoped guard.
- Migrate `discord.ui.TextInput.label` → `discord.ui.Label` in `tests/test_setup_module_tickets.py` to clear 18 `DeprecationWarning`s.

## SDD Cycle Complete

The change has been fully planned, implemented, verified, and archived. The archived audit trail reflects final state at `fa7dcea`; forward (higher-ranked) evidence outranks stale snapshots per Final-State Authority. Ready for the next change / v1.0.0.

