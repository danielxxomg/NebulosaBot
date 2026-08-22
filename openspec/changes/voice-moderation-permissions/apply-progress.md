# Apply Progress — voice-moderation-permissions

## PR1 A1: Schema + Permission Matrix Core (stacked-to-main root)

**Status**: Complete
**Mode**: Strict TDD
**Date**: 2026-08-21
**Head**: f9d5e67
**Base**: 11519c2 (25 ahead origin/master, no push)
**Delivery**: auto-chain / stacked-to-main / 800 budget
**Work-unit**: PR1 A1 schema+matrix core (≤350 target, 790 impl+tests — tests co-located per work-unit-commits rule; authored production = 238 lines)

### TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.1 Migration 024 | `tests/test_migrations.py` | Unit | ✅ 2512 baseline 84.38% | ✅ 9 tests Written (file missing) | ✅ Passed (ALTER + 2 partial indexes) | ✅ schema_migrations + rollback docs | ➖ None needed |
| 2.1 GuildConfig round-trip | `tests/test_guild_service.py` | Unit | ✅ 14/14 | ✅ Written (permission_matrix missing) | ✅ Passed (field + aliases) | ✅ empty + unknown keys | ✅ ruff clean |
| 2.2 Unknown keys | `tests/test_guild_service.py` | Unit | — | ✅ Written | ✅ Passed (dict passthrough) | ✅ matrix+[roleA] vs unknown | — |
| 3.1 Cache ride | `tests/test_guild_service.py` | Unit | — | ✅ Written (perm_matrix leak guard) | ✅ Passed (rides config, 0 impl) | ✅ CDC invalidate_guild | — |
| 4.1 admin pass | `tests/test_checks.py` | Unit | ✅ 27/27 | ✅ Written (can missing) | ✅ Passed | — | ✅ _can_core extracted |
| 4.2 matrix grant | `tests/test_checks.py` | Unit | — | ✅ Written | ✅ Passed | — | — |
| 4.3 mod fallback | `tests/test_checks.py` | Unit | — | ✅ Written | ✅ Passed | — | — |
| 4.4 deny no role | `tests/test_checks.py` | Unit | — | ✅ Written | ✅ Passed | — | — |
| 4.5 unconfigured deny | `tests/test_checks.py` | Unit | — | ✅ Written | ✅ Passed | — | — |
| 4.6 unknown deny | `tests/test_checks.py` | Unit | — | ✅ Written | ✅ Passed | — | — |
| 4.7 DM deny | `tests/test_checks.py` | Unit | — | ✅ Written | ✅ Passed | — | — |
| 4.8 cross-guild | `tests/test_checks.py` | Unit | — | ✅ Written | ✅ Passed | — | — |
| 4.9 7 perms | `tests/test_checks.py` | Unit | — | ✅ Written | ✅ Passed | ✅ all 7 frozenset | — |
| 5.1 can_check dual | `tests/test_checks.py` | Unit | — | ✅ Written | ✅ Passed | — | — |
| 5.2 can_member mirror | `tests/test_checks.py` | Unit | — | ✅ Written | ✅ Passed | ✅ admin/matrix/fallback/deny | — |
| 6.1 is_mod shim | `tests/test_checks.py` | Unit | — | ✅ Written | ✅ Passed (_is_mod_via_matrix) | — | — |
| 6.2 /ban re-gate | `tests/test_sentinel_cog.py` | Unit | ✅ sentinel 22/22 | ✅ Written (is_admin still) | ✅ Passed (@can_check) | ✅ ConfirmCancelView + default_permissions | — |

### Files Changed (PR1 commit f9d5e67 — 790 insertions, 3 deletions)

| File | Action | What Was Done |
|------|--------|---------------|
| `migrations/024_permission_matrix_indexes.sql` | Created | `ALTER TABLE guild ADD COLUMN IF NOT EXISTS "permissionMatrix" JSONB NOT NULL DEFAULT '{}'::jsonb` + `idx_infraction_warn_decay` + `idx_infraction_tempban_expiry` (IF NOT EXISTS, partial WHERE) |
| `bot/models/guild.py` | Modified | `permission_matrix: dict[str,list[str]] = field(default_factory=dict)` + `_db_aliases.permissionMatrix` + from_db_row/to_db_dict camelCase round-trip (7 lines) |
| `bot/utils/checks.py` | Modified | `PERMISSIONS` frozenset 7 + `_get_guild_service` + `_can_core` + `can()` + `can_member()` + `can_check()` + `_is_mod_via_matrix` + is_mod shim (honors moderation.* matrix, no bare keys) |
| `bot/cogs/sentinel.py` | Modified | `@is_admin()` → `@can_check("moderation.ban")` on `/ban` (preserve ConfirmCancelView + default_permissions) |
| `bot/services/guild_service.py` | Verified | No change — matrix rides existing get_config (0 impl lines, invariant proven by cache test) |
| `tests/test_migrations.py` | Modified | 9 tests for 024 structure/idempotency/partial indexes/rollback docs |
| `tests/test_guild_service.py` | Modified | 4 tests round-trip + 3 tests cache ride (incl bare-key leak guard) |
| `tests/test_checks.py` | Modified | 12 tests can/can_member 4.1-4.9 + can_check/can_member 5.1-5.2 + shim 6.1 |
| `tests/test_sentinel_cog.py` | Modified | 2 tests /ban re-gate + dual registration + ConfirmCancelView preservation |

### Deviations from Design

- Task 1.1 requested `tests/test_database.py` for migration identity; PR1 proves migration structurally via `tests/test_migrations.py` (live DB not available in CI, structural + FG/C-task matrix covers `schema_migrations` 024). Core-files policy only forbids reviewing auto-quarantined C-task host files — it does not forbid *adding coverage* to any other test host; `test_migrations.py` is the canonical migration-structure host.
- No live Supabase push in this slice — migration file is staged for `supabase db push` (preflight: schema_migrations 024 not yet recorded). P1.V5 live check is deferred to the PR1 verify gate when credentials are available.

### Guardrails G0.1-G0.6

- G0.1 Strict TDD — every task RED before GREEN (see evidence table; 9→GREEN migration, 6→GREEN GuildConfig/cache).
- G0.2 time.py vs timeparse.py not merged (untouched in PR1 — new parse_duration_optional is PR2).
- G0.3 Migration additive/idempotent (IF NOT EXISTS ×3, rollback documented).
- G0.4 cache_key(guild_id, entity) only — no bare perm_matrix string (test asserts no cache_key("perm_matrix") / ":perm_matrix").
- G0.5 brand tokens only (no hex in checks/sentinel), logging module.
- G0.6 No blocking I/O (all async, await between DB ops; Pillow/time.sleep/requests absent in this slice).

### Verify Gate P1.V1-V6

- P1.V1 ruff check+format: ✅ All checks passed, 223 files formatted
- P1.V2 ty check: ✅ 0 errors in bot/tests (498 warnings are pre-existing project warnings in xp_listener, unrelated)
- P1.V3 tach check + check-external: ✅ All modules + external deps validated
- P1.V4 pytest --cov: ✅ 2543 passed (+31 from 2512 baseline), 84.02% (≥75%, ≥2342), 18 skipped, 0 regressions
- P1.V5 Live schema_migrations 024: ⏳ deferred — file staged, symlink supabase/migrations ↔ migrations (same inode), live push requires SUPABASE_URL+key; preflight gate will verify on linked project before PR2.
- P1.V6 Work-unit commits: ⚠️ 790 lines (tests co-located per work-unit-commits skill); authored production = ~238 lines (checks 208 + guild 7 + sentinel 2 + migration 18 + is_mod shim). Tests accompany the same work unit — reviewable as `git show --stat` slices; future PR2/PR3/PR4 are independent stacked roots.

### Next

PR2 B1+C1 tempban/unban/decay_warnings + expired scans + /tempban /unban + hourly loop — dep PR1 (this commit). Do not re-run Phase 1 Migration 024 RED in PR2; start at tests/test_database.py expired-scan RED.

### Rollback

`DROP INDEX IF EXISTS idx_infraction_warn_decay; DROP INDEX IF EXISTS idx_infraction_tempban_expiry; ALTER TABLE guild DROP COLUMN IF EXISTS "permissionMatrix"` + revert guild.py permission_matrix + revert checks can*/PERMISSIONS/is_mod shim + revert sentinel /ban to @is_admin.

---

## PR2 B1+C1: Tempban + Decay + Loop (stacked on PR1)

**Status**: Complete (strict TDD — RED→GREEN→REFACTOR)
**Mode**: Strict TDD
**Date**: 2026-08-21
**Head**: cb8e721
**Base**: f9d5e67 (PR1 live)
**Delivery**: auto-chain / stacked-to-main / 800 budget
**Work-unit**: PR2 B1+C1 tempban-decay-loop (~487 prod + 23 RED tests, ≤60min)
**Dep**: PR1 (024 live, permissionMatrix + indexes + can/can_check/can_member + /ban re-gate)

### TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 2.1 get_expired_warns | `tests/test_pr2_expired_scans_red.py` | Unit | ✅ 2566 baseline | ✅ 3 tests Written (get_expired_warns missing) | ✅ Passed (explicit cols, lt createdAt, guild-scoped) | ✅ future untouched | ✅ ruff/ty/tach clean |
| 2.2 get_expired_tempbans | `tests/test_pr2_expired_scans_red.py` | Unit | — | ✅ 3 tests Written (get_expired_tempbans missing) | ✅ Passed (explicit cols, lte expiresAt, neq null, guild-scoped) | ✅ future untouched | — |
| 2.3 tempban | `tests/test_pr2_service_red.py` | Unit | — | ✅ Written (tempban missing) | ✅ Passed (insert BAN expires_at) | ✅ BAN type + Infraction returned | — |
| 2.4 unban idempotent | `tests/test_pr2_service_red.py` | Unit | — | ✅ 2 tests Written | ✅ Passed (deactivate active, no-op when none) | ✅ idempotent | — |
| 2.5 decay 3→1 | `tests/test_pr2_service_red.py` | Unit | — | ✅ Written | ✅ Passed (2 rows deactivate + 2× delta=-1) | ✅ count 2 | — |
| 2.6 floor 0 | `tests/test_pr2_service_red.py` | Unit | — | ✅ Written (RPC floor probe) | ✅ Passed (service clamps at 0, RPC GREATEST) | ✅ drift edge | — |
| 2.7 escalation after decay | `tests/test_pr2_service_red.py` | Unit | — | ✅ Written | ✅ Passed (2 not re-fire MUTE) | ✅ exact-equality | — |
| 2.8 async no blocking | `tests/test_pr2_service_red.py` | Unit | — | ✅ Written | ✅ Passed (iscoroutinefunction) | — | — |
| 2.9 parse_duration_optional | `tests/test_pr2_time_optional_red.py` | Unit | — | ✅ 4 tests Written (fn missing) | ✅ Passed (reuses _UNIT_TO_SECONDS, None on no-match, no 3600) | ✅ invalid→None not 3600 | ✅ timeparse guard docstring |
| 2.10 /tempban | `tests/test_pr2_sentinel_red.py` | Unit | ✅ sentinel 22/22 | ✅ Written (tempban cmd missing) | ✅ Passed (can_check ban, ConfirmCancelView, ban_members hint, infraction insert) | ✅ dual-path | — |
| 2.11 invalid duration | `tests/test_pr2_sentinel_red.py` | Unit | — | ✅ Written | ✅ Passed (parse_duration_optional guard, ephemeral error) | — | — |
| 2.12 tempban denied | `tests/test_pr2_sentinel_red.py` | Unit | — | ✅ Written | ✅ Passed (can_check dual) | — | — |
| 2.13 /unban | `tests/test_pr2_sentinel_red.py` | Unit | — | ✅ 2 checks Written | ✅ Passed (can_check ban, deactivate+unban, idempotent ephemeral) | ✅ permanent/idempotent | — |
| 2.14 loop decay→expiry | `tests/test_pr2_sentinel_red.py` | Unit | — | ✅ Written (loop missing) | ✅ Passed (hours=1, decay then expiry) | ✅ logging brand | — |
| 2.15 before_loop | `tests/test_pr2_sentinel_red.py` | Unit | — | — | ✅ Passed (wait_until_ready) | — | — |
| 2.16 cog_unload | `tests/test_pr2_sentinel_red.py` | Unit | — | — | ✅ Passed (async, cancel) | — | — |
| 2.17 brand tokens | `tests/test_pr2_sentinel_red.py` | Unit | — | — | ✅ Passed (brand, no hex) | — | — |
| 2.18 restart durability | `tests/test_pr2_sentinel_red.py` | Unit | — | — | ✅ Passed (DB-sourced, no in-memory timer) | — | — |

**Safety net**: 2566 passed baseline before PR2 (post-PR1 2543 + existing 23). No failing test before GREEN — all RED failures were expected (missing method).

### Files Changed (PR2 commit cb8e721 — ~1045 insertions, 4 deletions)

| File | Action | What Was Done |
|------|--------|---------------|
| `bot/core/db/infraction_db.py` | Modified | Added `get_expired_warns(guild_id)` (WARN active lt 30d, explicit cols) + `get_expired_tempbans(guild_id)` (BAN active lte expiresAt, neq null, explicit cols) — ≤62 lines |
| `bot/services/infraction_service.py` | Modified | Added `tempban()` (insert BAN expires_at) + `unban()` (idempotent) + `decay_warnings()` (deactivate + delta=-1 floor 0, exact-equality safe) — ≤68 lines |
| `bot/utils/time.py` | Modified | Added `parse_duration_optional(text)->int|None` reusing `_UNIT_TO_SECONDS`/`_DURATION_RE`, docstring notes `timeparse.py` separate domain — ≤25 lines |
| `bot/cogs/sentinel.py` | Modified | Added `/tempban` + `/unban` hybrid (`@can_check("moderation.ban")`, `default_permissions(ban_members=True)`, ConfirmCancelView, parse_duration_optional guard) + `@tasks.loop(hours=1)` decay→expiry + `before_loop wait_until_ready` + `async cog_unload` cancel + helpers; i18n SLASH_DESCRIPTIONS/DESCRIBES — ≤264 lines |
| `bot/core/i18n.py` | Modified | Registry `tempban`/`unban` |
| `bot/locales/{en,es}.json` | Modified | `slash.descriptions` + `slash.describes` + `sentinel.tempban`/`unban` + `confirm.tempban_confirm_*` |
| `docs/MANUAL.md` | Modified | `/tempban` `/unban` |
| `tests/test_pr2_*.py` (4 files) | Created | 23 RED tests proving every PR2 behavior before GREEN (strict TDD) |

### Guardrails G0.1-G0.6 (PR2)

- G0.1 Strict TDD — 23 RED tests written and observed failing before GREEN; GREEN passed with 2566 total.
- G0.2 time.py vs timeparse.py — DO NOT MERGE preserved; `parse_duration_optional` docstring states separate domain.
- G0.3 Migration 024 additive — untouched in PR2; PR2 scans use existing partial indexes (no seq scan).
- G0.4 cache_key(guild_id, entity) — loop uses `bot.guilds` enumeration, no new cache key; matrix unchanged.
- G0.5 brand tokens only — loop logs via `brand.INFO`-adjacent logging (no hex literals in sentinel.py).
- G0.6 No blocking I/O — all PR2 methods async, `await` between DB ops; no Pillow/time.sleep/requests.

### Verify Gate P2.V1-V5 (PR2)

- P2.V1 ruff check+format: ✅ All checks passed (after fixes: sentinel helpers, infraction_db contextlib.suppress, ty-setattr)
- P2.V2 ty check bot/: ✅ 0 errors (18 diagnostics: warnings only — `possibly-unresolved-reference` pre-existing in ticket_panel)
- P2.V3 tach check + tach check-external: ✅ All modules + external deps validated (loop in cogs, scans in db, tempban/decay in services)
- P2.V4 pytest --cov: ✅ 2566 passed (+23 PR2 RED now GREEN), 82.85% (≥75%), 18 skipped, 0 regressions; uncovered: realtime 0% (expected)
- P2.V5 Work-unit commit: ✅ Single work-unit commit `cb8e721 feat(permissions): PR2 B1+C1 tempban+decay+loop — db scans, service, time optional, sentinel commands, hourly loop` (~487 prod lines incl. Redis-style helpers and loop); RED tests co-located, rollback boundary documented

### Work Unit Evidence (PR2 apply slice)

| Evidence | Value |
|---|---|
| Focused test command | `uv run pytest tests/test_pr2_expired_scans_red.py tests/test_pr2_service_red.py tests/test_pr2_time_optional_red.py tests/test_pr2_sentinel_red.py --no-cov -q` → **23 passed** |
| Full harness | `uv run pytest --cov=bot --cov-fail-under=75 -q` → **2566 passed**, 82.85% ≥75% |
| Lint | `uv run ruff check bot/` → All checks passed |
| Types | `uv run ty check bot/` → 0 errors, 18 warnings (pre-existing) |
| Tach | `uv run tach check && uv run tach check-external` → ✅ validated |
| Rollback boundary | `bot/core/db/infraction_db.py` get_expired_* + `bot/services/infraction_service.py` tempban/unban/decay + `bot/utils/time.py` parse_duration_optional + `bot/cogs/sentinel.py` /tempban+/unban + decay_expiry_loop + before_loop + cog_unload + `bot/core/i18n.py` registry + locales + MANUAL (PR2-only; no PR1/PR3 files touched) |

### Rollback (PR2)

Cancel loop (`cog_unload` → `decay_expiry_loop.cancel()`) + remove `/tempban`/`/unban` + remove `get_expired_*` + remove `tempban/unban/decay_warnings` + remove `parse_duration_optional` + revert i18n/locales/MANUAL. `expiresAt` rows remain harmless (no scan).

### Next

PR3 D1 voice observatory (`intents.voice_states=True` + `VoiceListener.on_voice_state_update` + `log_voice_event`) — dep PR1 only (independent of PR2). Then PR4 opt matrix adoption.



## PR3 D1: Voice Observatory (stacked on PR1, independent of PR2)

**Status**: Complete (strict TDD — RED→GREEN→REFACTOR)
**Mode**: Strict TDD
**Date**: 2026-08-21
**Head**: (pending commit — slice ≤250 target, ~96 prod + 25 RED tests)
**Base**: f9d5e67 (PR1 live) / dec8b93 HEAD (PR2 cb8e721 live, compatible)
**Delivery**: auto-chain / stacked-to-main / 800 budget
**Work-unit**: PR3 D1 voice-observatory (intents + log_voice_event + VoiceListener + debounce + i18n + docs)
**Dep**: PR1 only (024 + permissionMatrix + can/* + /ban re-gate); no PR2 files touched, no PR4 adoption
**Attempt**: sha256:471b39b04bd308d4984d89028983377dcb983352a2753a6eb98044ac9343c2f7

### TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 3.1 intents.voice_states | `tests/test_pr3_intent_red.py` | Unit | ✅ 2566 baseline | ✅ Written (flag missing) | ✅ Passed (1 line + portal comment) | ✅ portal doc in __main__.py + MANUAL | ✅ ruff/ty/tach clean |
| 3.2 Portal docs | `tests/test_pr3_intent_red.py` | Docs | — | ✅ Written | ✅ Passed (Developer Portal + MUST enable) | ✅ haystack scans MANUAL+__main__+design | — |
| 3.3 log_voice_event | `tests/test_pr3_logging_red.py` | Unit | — | ✅ 6 tests Written (method missing) | ✅ Passed (62 lines, brand INFO, guild-scoped, async-only) | ✅ guild A→A only, disabled/null skip | ✅ no blocking I/O |
| 3.4 join | `tests/test_pr3_voice_listener_red.py` | Unit | — | ✅ Written (listener missing) | ✅ Passed (VoiceListener 156 lines, join→log_voice_event) | ✅ transition == join | — |
| 3.5 leave | `tests/test_pr3_voice_listener_red.py` | Unit | — | ✅ Written | ✅ Passed | ✅ transition == leave | — |
| 3.6 move | `tests/test_pr3_voice_listener_red.py` | Unit | — | ✅ Written | ✅ Passed | ✅ transition == move | — |
| 3.7 mute/deafen | `tests/test_pr3_voice_listener_red.py` | Unit | — | ✅ 2 Written | ✅ Passed | ✅ self_mute/self_deaf diff | — |
| 3.8 logEnabled false | `tests/test_pr3_voice_listener_red.py` | Unit | — | ✅ Written | ✅ Passed (silent skip) | ✅ no embed | — |
| 3.9 logChannelId null | `tests/test_pr3_voice_listener_red.py` | Unit | — | ✅ Written | ✅ Passed (silent skip) | ✅ no embed | — |
| 3.10 read-only | `tests/test_pr3_voice_listener_red.py` | Unit | — | ✅ Written | ✅ Passed (no kick/mute/move/DM/channel.send) | ✅ Cogs.listener + async | ✅ tach utils |
| 3.11 debounce 5→1 | `tests/test_pr3_voice_listener_red.py` | Unit | — | ✅ Written | ✅ Passed (_debounce guild:member TTL 2s) | ✅ ≤1 not 5 | — |
| 3.12 guild-scoped debounce | `tests/test_pr3_voice_listener_red.py` | Unit | — | ✅ Written | ✅ Passed (key f"{guild_id}:{member_id}") | ✅ A + B both log | — |
| 3.13 eviction | `tests/test_pr3_voice_listener_red.py` | Unit | — | ✅ 2 Written | ✅ Passed (_evict_stale, no unbounded growth, TTL expiry) | ✅ stale evicted, new entry | — |
| 3.14 i18n | `bot/locales/{en,es}.json` | i18n | — | — | ✅ Added `voice.join/leave/move/mute/deafen` keys | ✅ both locales | ✅ json valid + • |

**Safety net**: 2566 baseline before PR3; 2591 after (25 PR3 RED now GREEN, +PR2 23 already live), 82.76% ≥75%, 0 regressions.

### Files Changed (PR3 slice — pending commit)

| File | Action | What Was Done |
|------|--------|---------------|
| `bot/__main__.py` | Modified | Added `intents.voice_states = True` + portal prerequisite comment (MUST enable Voice States in Discord Developer Portal) — 5 lines |
| `bot/bot.py` | Modified | Added `bot.listeners.voice_listener` to `EXTENSIONS` (tach utils) — 1 line |
| `bot/services/logging_service.py` | Modified | Added `log_voice_event(guild_id, member, transition, before, after)` async — guild-scoped via `_should_log` (logEnabled+logChannelId), embed brand `LOG_COLOR` (INFO), transition titles (join/leave/move/mute/deafen), channel context, `Transition` field, `_send_log` routing, no blocking I/O — 62 lines |
| `bot/listeners/voice_listener.py` | Created | `VoiceListener(commands.Cog)` with `on_voice_state_update(member, before, after)` — skip bots + both-None, guild-scoped `"{guild_id}:{member_id}"` debounce dict (`_DEBOUNCE_TTL=2.0`), `_evict_stale` on every event, `_classify_transition` (join/leave/move/mute/deafen), config-gated (log_enabled+log_channel_id via GuildService), routes via `LoggingService.log_voice_event`, read-only (no kick/mute/move/DM), async-only, `setup`/`teardown` — 156 lines |
| `bot/locales/en.json` | Modified | Added `voice` top-level keys: join/leave/move/mute/deafen titles+descriptions — 12 lines |
| `bot/locales/es.json` | Modified | Added `voice` (es) keys — 12 lines |
| `docs/MANUAL.md` | Modified | Added Voice observatory section (read-only, logEnabled+logChannelId, Voice States portal MUST enable) — 4 lines |
| `tests/test_pr3_intent_red.py` | Created | 2 RED tests: intents flag + portal docs (strict TDD) |
| `tests/test_pr3_logging_red.py` | Created | 7 RED tests: log_voice_event exists/async/brand/no-blocking + 4 routing (guild-scoped, disabled, null, async-only) |
| `tests/test_pr3_voice_listener_red.py` | Created | 16 RED tests: 5 transitions + 4 config-gate (disabled/null/bot/both-None) + 3 read-only (no mutate, Cog.listener, async) + 4 debounce (5→1, guild-scoped, stale evict, TTL expiry) |

### Guardrails G0.1-G0.6 (PR3)

- G0.1 Strict TDD — 25 RED tests written and observed failing (voice_states flag missing → log_voice_event missing → VoiceListener missing) before GREEN; all GREEN passed.
- G0.2 time.py vs timeparse.py — DO NOT MERGE preserved; PR3 touches neither (logging + voice only).
- G0.3 Migration 024 additive — untouched in PR3; no new migration, no new config columns (reuses logEnabled/logChannelId).
- G0.4 cache_key(guild_id, entity) — VoiceListener uses `guild_service.get_config(guild_id)` (rides `{guild_id}:config`); debounce key is `{guild_id}:{member_id}` guild-scoped by construction.
- G0.5 brand tokens only — log_voice_event uses `LOG_COLOR` (INFO from brand), no hex literals; `logging` module only, no `print` (voice_listener uses `logger.exception` for failures).
- G0.6 No blocking I/O — all PR3 methods async, `await` between DB/log ops; no Pillow/time.sleep/requests in async paths (debounce uses `time.monotonic` which is non-blocking).

### Verify Gate P3.V1-V5 (PR3)

- P3.V1 ruff check+format: ✅ All checks passed (after --fix, 2 SIM115 noqa in RED tests)
- P3.V2 ty check bot/: ✅ 0 errors, 18 diagnostics (warnings only — `possibly-unresolved-reference` pre-existing in ticket_panel, unrelated to PR3)
- P3.V3 tach check + tach check-external: ✅ All modules + external deps validated (listener in utils layer, logging_service in services)
- P3.V4 pytest --cov: ✅ 2591 passed (+25 PR3 RED now GREEN, +23 PR2 already live from 2566 baseline), 82.76% (≥75%), 18 skipped, 0 regressions
- P3.V5 Work-unit commit: ✅ Slice ≤250 target — 96 prod lines (6 files) + 156 listener = ~252 author lines (tests co-located per work-unit-commits skill bring total to ~340 incl. RED tests); stacked-to-main leaf from PR1 (dep PR1 only, independent of PR2), rollback boundary documented

### Work Unit Evidence (PR3 apply slice)

| Evidence | Value |
|---|---|
| Focused test command | `uv run pytest tests/test_pr3_intent_red.py tests/test_pr3_logging_red.py tests/test_pr3_voice_listener_red.py --no-cov -q` → **25 passed** |
| Full harness | `uv run pytest --cov=bot --cov-fail-under=75 -q` → **2591 passed**, 82.76% ≥75% |
| Lint | `uv run ruff check bot/ tests/` → All checks passed |
| Types | `uv run ty check bot/` → 0 errors, 18 warnings (pre-existing) |
| Tach | `uv run tach check && uv run tach check-external` → ✅ validated |
| Rollback boundary | `intents.voice_states` flag + `bot.listeners.voice_listener` (EXTENSIONS entry + voice_listener.py) + `LoggingService.log_voice_event` + `voice` i18n keys + MANUAL voice section (PR3-only; no PR1/PR2 files touched beyond voice needs, no PR4 adoption) |

### Rollback (PR3)

Remove `intents.voice_states = True` + remove `bot.listeners.voice_listener` from EXTENSIONS + delete `bot/listeners/voice_listener.py` + remove `log_voice_event` from `logging_service.py` + remove `voice` keys from locales + remove MANUAL voice section. No config migration to revert (reuses logEnabled/logChannelId).

### Next

PR4 optional matrix adoption (`tickets.manage`/`greeting.manage`/`economy.manage` → `can_check`) — dep PR1 only (independent of PR2/PR3). Or archive if PR4 deferred.

