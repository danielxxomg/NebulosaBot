# Archive Report — voice-moderation-permissions (Cycle 3 of 3)

**Archived**: 2026-08-21
**Change**: voice-moderation-permissions
**Cycle**: 3 of 3 (qa-modernization → welcome-neon-timer-banana → **voice-moderation-permissions**)
**Head at archive**: `5e16318` (31 commits ahead of `origin/master`, base `f77bf38`)
**Artifact store**: OpenSpec (`openspec/changes/archive/2026-08-21-voice-moderation-permissions/`)

---

## Final State (Terminal Authority)

Per `verify-report.md` (evidence_revision `sha256:d38bc653277b13a2db0ad0eaa14ab4cd4a704aa5d920bcbbd9aae006f2bab97d`), verified at head `5e16318` after remediation:

| Metric | Final Value |
|--------|-------------|
| Verdict | `pass` |
| Requirements | 20/20 |
| Scenarios | 63/63 (✅ COMPLIANT, 0 PARTIAL, 0 FAILING, 0 UNTESTED) |
| Tests | 2617 passed, 18 skipped, 0 failed |
| Coverage | 83.87% (threshold 75%) |
| Assertion quality | 0 CRITICAL, 0 blocking tautologies |
| Blockers | 0 |
| Critical findings | 0 |

**Test run**: `uv run pytest --cov=bot -q --cov-fail-under=75` → exit 0, output hash `sha256:bb5f33f37edd5cfbfe63593895de3a8c677926a15e79c3ed7a2df15730af21fd`.
**Build run**: `uv run ruff check bot/ tests/ && uv run ruff format --check bot/ tests/ && uv run ty check bot/ tests/ && uv run tach check && uv run tach check-external` → exit 0, output hash `sha256:b995203d7a27e806979c40033c55adb3ef937ce2f23395f1f539526b70f06654`.
**Focused suite**: `uv run pytest tests/test_checks.py tests/test_migrations.py tests/test_pr2_* tests/test_pr3_* tests/test_pr4_* --no-cov -q` → 316 passed.
**Remediation behavioral probes** (`/tempban`, `/unban`, loop, floor, read-only): 10 passed, 0 failed.

### Remediation History (prior FAIL → final PASS)

An earlier full verification at evidence_revision `sha256:11c60160b91cc42a980a55d574f2ca9ecc0be01be40cb540bea6024f44342881` returned **FAIL** with 6 CRITICAL blockers. That snapshot is preserved as history but is **not** the state at close. The blockers were remediated in commit `5e16318` (attempt ordinal 6, `remediates_evidence_revision` pointing at the failed report), settled `complete` per `gentle-ai sdd-attempt status`:

| Blocker (FAIL snapshot) | Remediation (commit 5e16318) | Final (PASS) |
|---|---|---|
| Tempban final visibility was ephemeral | `bot/cogs/sentinel.py` closes the ephemeral confirmation via `interaction.response.edit_message`, then sends the final action through `ctx.channel.send` (permanent) | ✅ Resolved |
| Loop ran `logger.info` / business logic in cog | Expiry delegated to `InfractionService.expire_tempbans`; both decay and expiry phases call `LoggingService.log_sentinel_loop` | ✅ Resolved |
| Behavioral command/loop coverage gap | Remediation-focused run executes real mocked callbacks for tempban, unban, loop order, readiness, cancellation, expiry delegation, warning floor, voice read-only | ✅ 10/10 passed |
| Warning-floor tautology (`assert True`) | `tests/test_pr2_service_red.py` deactivates an old WARN and asserts `update_member_warnings.assert_not_awaited()` when warnings are zero | ✅ Resolved |
| Voice read-only tautology (`or True`) | `tests/test_pr3_voice_listener_red.py` executes the listener and asserts every forbidden mutation mock was not awaited | ✅ Resolved |
| Live migration link unproven | `supabase migration list` exits 0 and reports `024` local / `024` remote | ✅ Resolved |

The current passing report (`sha256:d38bc653...`) is the state at close. The historical failed report is preserved in the archived `verify-report.md` envelope and never erased.

### Live Supabase Evidence (read-only)

- `supabase migration list` reports local `024` / remote `024` synchronized; linked remote project `vozkcckiybebhcclrasa` responded successfully.
- Migration `024_permission_matrix_indexes.sql` is additive + idempotent (`IF NOT EXISTS` ×3): `ALTER TABLE guild ADD COLUMN "permissionMatrix" JSONB NOT NULL DEFAULT '{}'::jsonb` + partial index `idx_infraction_warn_decay` (WHERE `type='WARN' AND active=true`) + partial index `idx_infraction_tempban_expiry` (WHERE `type='BAN' AND active=true AND "expiresAt" IS NOT NULL`).
- No new table introduced; 23 → 24 migrations live; RLS on 7 tables unchanged from Cycle 2.

---

## Goal

Cycle 3 of 3. Turn Sentinel into a subtle voice observatory and complete the moderation permissions story: add a granular per-guild permission matrix (`permissionMatrix` JSONB on `guild`), tempban/unban with 30-day warning decay, and a read-only voice listener. Guilds gain fine-grained control over seven moderation/staff permissions via a JSONB matrix, with `moderation.*` falling back to the existing single `modRoleId`. Voice activity is observed and logged, never acted on.

## Instructions

- **execution_mode**: auto
- **artifact_store.mode**: openspec
- **delivery_strategy**: auto-chain
- **chain_strategy**: stacked-to-main
- **review_budget_lines**: 800
- **strict_tdd**: true — RED (write failing test, watch fail) → GREEN (minimal code) → REFACTOR (stay green). No production code before a failing test.
- English for technical artifacts; Spanish reserved for design docs.
- Preserve prior-cycle deltas in main specs (append wrapped in `BEGIN/END DELTA` markers; do not delete history).
- No blocking I/O on the event loop; cache keys via `cache_key(guild_id, entity)` only; brand tokens only (no hex outside `brand.py`); `logging` module only.

## Discoveries

- **Permission matrix JSONB rides the existing `{guild_id}:config` cache** — no new cache key is introduced (cross-guild leak guard). CDC on the `guild` table already evicts the config entry including the matrix, so dashboard matrix edits propagate through the existing Realtime path with zero new cache plumbing.
- **`expiresAt` column goes from dead → live** with tempban. The column existed for BAN infractions but was unused until Cycle 3. `get_infractions` callers were audited in PR2 Phase 2 — no code path assumed `expiresAt IS NULL` for BAN, so the column activation is safe.
- **`intents.voice_states` is a portal prerequisite the bot cannot detect.** Documented in `bot/__main__.py` (prerequisite comment) and `docs/MANUAL.md` (voice observatory section). The bot silently receives no voice events if the guild owner has not enabled Voice States in the Discord Developer Portal.
- **Decay floor is defense-in-depth.** The service clamps `delta = min(delta, current)` (only decrements if `current > 0`), and RPC 009 `increment_member_warnings` also floors via `GREATEST(warnings, 0)`. Either layer alone would suffice; both exist so a future RPC change cannot make `Member.warnings` negative.
- **Escalation uses exact-equality** (`warnings_count == threshold`), so decay (3 → 1) + re-warn (→ 2) does NOT re-fire the MUTE threshold at 2. The decay invariant preserves this.
- **Loop is DB-sourced for restart durability** — `get_expired_tempbans` scans on every iteration; no in-memory timer survives a bot restart. Tempbans created before a restart are recovered on the next loop fire.
- **800-line review budget slicing was needed.** Total lifetime changed lines = 4116 across 6 attempts. PR1 (793, prod 238) and PR2 (1215, prod 487) exceeded the 800 slice budget and required maintainer `size:exception` approval (RED tests co-located per work-unit-commits); PR3 (1062, prod 252) was reset and re-scoped; PR4 (446, prod 87) fit. Each slice remained a reviewable stacked-to-main leaf.
- **Two Strict-TDD test tautologies were caught at verification** (`assert True` in the warning-floor test, `or True` in the voice read-only test) and replaced with behavioral assertions in the remediation commit. This is the TDD discipline the project enforces paying off.
- **`bot/utils/time.py` vs `bot/utils/timeparse.py` remain separate domains** — `time.py` parses human duration strings → seconds (Sentinel); `timeparse.py` parses DB timestamp values → `datetime` (economy). The new `parse_duration_optional` lives in `time.py` with a docstring stating `timeparse.py` is separate.

## Accomplished

- ✅ **PR1 A1 — Schema + Permission Matrix Core** (commit `f9d5e67`, 790 insertions, authored prod 238). Migration 024 additive + idempotent; `GuildConfig.permission_matrix` camelCase round-trip; `can()`/`can_check()`/`can_member()` resolver (DM→deny, admin→True, matrix role grant, `moderation.*` → modRoleId fallback, deny-default, cross-guild isolation); `is_mod` shim honors matrix keys; `/ban` re-gated to `@can_check("moderation.ban")`. **2543 passed, 84.02% coverage, ruff/ty/tach green.**
- ✅ **PR2 B1+C1 — Tempban + Decay + Loop** (commit `cb8e721`, ~1045 insertions, authored prod ~487). `get_expired_warns`/`get_expired_tempbans` DB scans (explicit cols, guild-scoped, partial indexes); `InfractionService.tempban`/`unban`/`decay_warnings` (floor 0, exact-equality escalation preserved, async no-blocking); `parse_duration_optional` in `time.py`; `/tempban`+`/unban` hybrid commands with `ConfirmCancelView`; `@tasks.loop(hours=1)` decay→expiry with `before_loop`/`cog_unload`. **2566 passed, 82.85% coverage, ruff/ty/tach green.** (size:exception — prod 487 > 800 slice budget; RED tests co-located.)
- ✅ **PR3 D1 — Voice Observatory** (commit `6c24b4b`, ~340 insertions, authored prod ~96). `intents.voice_states=True` + portal docs; `LoggingService.log_voice_event` (guild-scoped, async, brand INFO, silent skip on disabled/null-channel); `VoiceListener` cog with `on_voice_state_update` (join/leave/move/mute/deafen classification, per-member `{guild_id}:{member_id}` TTL debounce, stale eviction, read-only — no kick/mute/move/DM); i18n keys. **2591 passed, 82.76% coverage, ruff/ty/tach green.**
- ✅ **PR4 — Optional Matrix Adoption** (commit `9803c85`, ~96 insertions, authored prod ~87). `bot/cogs/tickets.py` 16 lifecycle decorators `@is_mod()` → `@can_check("tickets.manage")` (`delete_category` stays `@is_admin`); `bot/cogs/greetings.py` `_admin_guard` rewritten to `await can("greeting.manage")`; economy `economy.manage` assessed N/A (dashboard-only, no bot manage surface). **2602 passed, 82.79% coverage, ruff/ty/tach green.**
- ✅ **Remediation** (commit `5e16318`, ~600 insertions, authored prod ~200). Resolved 6 CRITICAL blockers from the failed verification (tempban ephemeral→permanent via `ctx.channel.send`; loop business logic moved to `InfractionService.expire_tempbans` + `LoggingService.log_sentinel_loop`; 2 tautologies replaced with behavioral assertions; live 024/024 relink proven; behavioral probes added). Settled `complete` (attempt ordinal 6, `remediates_evidence_revision` = failed report). **2617 passed, 83.87% coverage, ruff/ty/tach green, 024/024 live.**
- ✅ **Spec compliance**: 20/20 requirements, 63/63 scenarios COMPLIANT at close.
- ✅ **SDD cycle complete**: proposal → explore → spec (6 delta specs) → design → tasks (84/84) → apply (4 PRs + remediation) → verify (PASS) → archive.

### Workload Summary

| Slice | Commit | Changed lines | Authored prod | Tests | Coverage | Notes |
|-------|--------|-------------:|--------------:|------:|---------:|-------|
| PR1 A1 | `f9d5e67` | 793 | 238 | 2543 | 84.02% | size:exception (tests co-located) |
| PR2 B1+C1 | `cb8e721` | 1215 | 487 | 2566 | 82.85% | size:exception (RED tests co-located) |
| PR3 D1 | `6c24b4b` | 1062 | 252 | 2591 | 82.76% | reset + re-scoped; size:exception |
| PR4 opt | `9803c85` | 446 | 87 | 2602 | 82.79% | fits budget |
| Remediation | `5e16318` | 600 | ~200 | 2617 | 83.87% | settled 6 blockers |
| **Lifetime** | — | **4116** | **~1264** | **2617** | **83.87%** | 6 attempts |

Stack: `main ├─📍PR1 (f9d5e67 live) ├─PR2 (cb8e721) ├─PR3 (6c24b4b) └─PR4 (9803c85) → remediation 5e16318`. Each leaf reviewable stacked-to-main; base `f77bf38` (v0.8.0-qa-modernization); master `11519c2`→`5e16318` is 31 commits ahead of `origin/master` without push; 60+1 SDDs.

## Next Steps

- **Push 31 commits to `origin/master`** — the change is verified and archived but not yet pushed (master is 31 commits ahead of `origin/master`). Pre-push receipt validation applies per SDD policy.
- **Enable the Voice States intent toggle in the Discord Developer Portal** (prerequisite for the voice observatory; the bot cannot detect a missing grant — documented in `bot/__main__.py` + `docs/MANUAL.md`).
- **Follow-up hardening (non-blocking)** — per verify-report SUGGESTION: add direct `/ban` matrix/fallback command callback tests and a controlled process-restart loop harness in a future hardening change. Current coverage proves behavior through the shared gate and source guards; a live Discord integration harness would add direct command-callback evidence. This does not block the current cycle.

## Relevant Files

- `migrations/024_permission_matrix_indexes.sql` — additive JSONB column + 2 partial indexes (live 024/024).
- `bot/models/guild.py` — `permission_matrix` field + camelCase round-trip.
- `bot/utils/checks.py` — `PERMISSIONS` frozenset (7) + `can`/`can_check`/`can_member` + `is_mod` shim (`_is_mod_via_matrix`).
- `bot/utils/time.py` — `parse_duration_optional` (separate domain from `timeparse.py`).
- `bot/core/db/infraction_db.py` — `get_expired_warns`/`get_expired_tempbans` (explicit cols, guild-scoped, partial indexes).
- `bot/services/infraction_service.py` — `tempban`/`unban`/`decay_warnings`/`expire_tempbans` (floor 0, exact-equality, async).
- `bot/services/logging_service.py` — `log_voice_event` + `log_sentinel_loop` (guild-scoped, async, brand INFO).
- `bot/cogs/sentinel.py` — `/ban` re-gate, `/tempban`+`/unban`, hourly decay→expiry loop (`before_loop`/`cog_unload`).
- `bot/cogs/tickets.py` — 16× `@can_check("tickets.manage")` (PR4).
- `bot/cogs/greetings.py` — `_admin_guard` → `can("greeting.manage")` (PR4).
- `bot/__main__.py` — `intents.voice_states=True` + portal prerequisite comment.
- `bot/listeners/voice_listener.py` — `VoiceListener` cog + per-member TTL debounce (read-only).
- `bot/locales/{en,es}.json` — tempban/unban/voice i18n keys.
- `docs/MANUAL.md` — `/tempban` `/unban` + voice observatory portal prerequisite section.
- `openspec/specs/permission-model/spec.md` — main spec updated (matrix resolver + dual-registration ADDED; ban + moderator MODIFIED).
- `openspec/specs/guild-config/spec.md` — main spec updated (matrix column + cache ride ADDED).
- `openspec/specs/infraction-service/spec.md` — main spec updated (decay/tempban/unban/floor/escalation/expiry ADDED).
- `openspec/specs/sentinel-commands/spec.md` — main spec updated (tempban/unban/loop ADDED).
- `openspec/specs/voice-observatory/spec.md` — main spec CREATED (full spec, mechanical copy).
- `openspec/specs/ephemeral-standard/spec.md` — main spec updated (tempban/unban visibility ADDED).

---

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| `permission-model` | Updated (merged) | 2 ADDED (matrix resolver, dual registration) + 2 MODIFIED (ban command, moderator check) — delta appended wrapped in `BEGIN/END DELTA` markers; prior deltas preserved |
| `guild-config` | Updated (merged) | 2 ADDED (permission matrix column, matrix read from config cache) — 6 scenarios |
| `infraction-service` | Updated (merged) | 6 ADDED (warn-decay, tempban, unban, decay floor, escalation, expired tempban) — 10 scenarios |
| `sentinel-commands` | Updated (merged) | 3 ADDED (tempban command, unban command, hourly loop) — 10 scenarios |
| `ephemeral-standard` | Updated (merged) | 1 ADDED (tempban confirmation ephemeral/permanent) — 3 scenarios |
| `voice-observatory` | Created (new) | Full spec mechanical copy (byte-identical, `diff -r` empty) — 4 requirements, 14 scenarios |

**Totals**: 20 requirements, 63 scenarios synced to main specs.

## Archive Contents

- proposal.md ✅
- explore.md ✅
- specs/ ✅ (6 delta specs: permission-model, guild-config, infraction-service, sentinel-commands, voice-observatory, ephemeral-standard)
- design.md ✅
- tasks.md ✅ (84/84 tasks complete — no unchecked implementation tasks)
- apply-progress.md ✅ (PR1-PR4 + remediation evidence)
- verify-report.md ✅ (final PASS `sha256:d38bc653...` preserved as evidence at close)
- archive-report.md ✅ (this file — additive)

## Mechanical Copy Verification

Per the Mechanical Copy Contract, all archive operations were performed via native shell commands (`cp -R`/`mv`) and verified with `diff -r`:

- **voice-observatory main spec creation** (mechanical copy): `diff -r` source vs destination → **empty** (byte-identical).
- **Change folder move to archive** (mechanical `mv`): pre-move recursive snapshot `cp -R` → `diff -r` snapshot vs archived tree → **empty** (byte-identical, no truncation or alteration). Source directory removed.

Verbatim `diff -r` output was empty in both cases — the only passing evidence. No file content passed through the model Read/Write path for copying.

## SDD Cycle Complete

The change has been fully planned, implemented, verified, and archived. Ready for the next change.
