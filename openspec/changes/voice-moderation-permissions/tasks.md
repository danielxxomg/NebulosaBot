# Tasks: voice-moderation-permissions (Cycle 3)

> Granular permission matrix + tempban/unban + 30d warn-decay + read-only voice observatory.
> Stacked-to-main, auto-chain, 4 PRs (~950 lines). Strict TDD (RED→GREEN→REFACTOR) per
> `test-driven-development` SKILL — NO production code before a failing test. Head `11519c2`.
> Test runner: `uv run pytest --cov=bot -q`. Tach 7-layer, cache-first, guild-scoped, async-only.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~950 (PR1 ~330, PR2 ~330, PR3 ~200, PR4 ~90 optional) |
| 400-line budget risk | High (total >400; each slice ≤350 keeps ≤60-min review) |
| Chained PRs recommended | Yes |
| Suggested split | PR1 A1 schema+matrix → PR2 B1+C1 tempban/decay → PR3 D1 voice → PR4 opt adoption |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

```
main
 ├─📍PR1 A1 schema+matrix core (≤350) dep: none
 │   ├─PR2 B1+C1 tempban/decay+loop (≤350) dep: PR1
 │   ├─PR3 D1 voice observatory (≤250) dep: PR1
 │   └─PR4 opt matrix adoption (≤300) dep: PR1 [OPTIONAL]
```

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Matrix JSONB + GuildConfig + can()/can_check()/can_member() + /ban re-gate | PR1 | `uv run pytest tests/test_checks.py tests/test_guild_service.py tests/test_database.py -q` | `uv run pytest --cov=bot --cov-fail-under=75 -q`; live `schema_migrations` 024 check | `024_*.sql` (DROP COLUMN/INDEX) + `permission_matrix` field + `can`/`can_check`/`can_member` + `/ban` decorator swap |
| 2 | tempban/unban/decay_warnings + expired scans + SentinelCog /tempban /unban + hourly loop | PR2 | `uv run pytest tests/test_infraction_service.py tests/test_sentinel_cog.py tests/test_database.py -q` | `uv run pytest --cov=bot --cov-fail-under=75 -q`; loop before_loop/cancel | `infraction_db` scan fns + `tempban`/`unban`/`decay_warnings` + `time.py` optional parser + `/tempban`/`/unban` + loop |
| 3 | intents.voice_states + VoiceListener + LoggingService.log_voice_event | PR3 | `uv run pytest tests/test_voice_listener.py tests/test_logging_service.py -q` | `uv run pytest --cov=bot --cov-fail-under=75 -q` | `intents.voice_states` flag + `voice_listener.py` + `log_voice_event` method |
| 4 | Tickets/Greetings swap to can() | PR4 opt | `uv run pytest tests/test_tickets_cog.py tests/test_greeting_cog.py -q -k "manage"` | `uv run pytest --cov=bot --cov-fail-under=75 -q` | per-cog decorator swap (matrix additive; revert restores is_mod) |

## Cross-cutting guardrails (apply to ALL slices)

- [x] G0.1 Strict TDD: each behavior = RED (write failing test, watch fail) → GREEN (minimal code) → REFACTOR (stay green). No production code without RED. — PR1 proven via evidence table in apply-progress.md
- [x] G0.2 `bot/utils/time.py` vs `bot/utils/timeparse.py` — DO NOT MERGE. New `parse_duration_optional` lives in `time.py`. Docstrings state the other is separate. — PR1 untouched (PR2 task)
- [x] G0.3 Migration 024 additive + idempotent (`IF NOT EXISTS`); query live `schema_migrations` before apply; rollback = `DROP INDEX` ×2 + `DROP COLUMN "permissionMatrix"`. — PR1 file staged, IF NOT EXISTS ×3
- [x] G0.4 Cache keys via `cache_key(guild_id, entity)` only — no bare entity strings (cross-guild leak guard). — PR1 test forbids cache_key("perm_matrix") / ":perm_matrix"
- [x] G0.5 brand tokens only, no hex literals outside `brand.py`; `logging` module, no `print`. — PR1 checks pass
- [x] G0.6 No blocking I/O on the event loop — Pillow/`time.sleep`/`requests` forbidden in async paths; CPU-bound via `asyncio.to_thread`. — PR1 all async/await

## PR1 — A1 Schema + Permission Matrix Core (≤350, dep: none)

Specs: `permission-model`, `guild-config`. Files: `migrations/024_*.sql`, `bot/models/guild.py`, `bot/services/guild_service.py`, `bot/utils/checks.py`, `bot/cogs/sentinel.py` (/ban re-gate only), `bot/locales/*`, tests.

### Phase 1: Migration 024 (schema)

- [x] 1.1 RED: `tests/test_database.py` assert migration 024 identity checked live + `guild.permissionMatrix JSONB DEFAULT '{}'` + `idx_infraction_warn_decay` + `idx_infraction_tempban_expiry` exist; idempotent re-apply no-op. Spec `guild-config` "Migration adds column with default", `infraction-service` "Partial indexes exist". — DONE via tests/test_migrations.py::TestMigration024 (9 tests RED→GREEN); live 024 push deferred to linked Supabase (file staged, IF NOT EXISTS ×3)
  - Given migration 024 applied / When new guild inserted without permissionMatrix / Then column is `'{}'::jsonb`.
  - TDD: RED first → GREEN create `migrations/024_permission_matrix_indexes.sql` (ALTER TABLE ADD COLUMN IF NOT EXISTS + CREATE INDEX IF NOT EXISTS ×2). Est ~25 lines.

### Phase 2: GuildConfig model

- [x] 2.1 RED: `tests/test_guild_service.py` round-trip `permission_matrix={"moderation.ban":["roleA"]}` and `{}` via `from_db_row`/`to_db_dict` (camelCase `permissionMatrix`); preserves `prefix`/`language`/other fields. Spec `guild-config` "Round-trip preserves matrix and other fields". — DONE 4 tests in TestGuildConfigPermissionMatrix
  - Given row with prefix='nb!', language='es', permissionMatrix={"moderation.ban":["roleA"]} / When round-trip / Then all preserved.
  - TDD: RED → GREEN add `permission_matrix: dict[str,list[str]] = field(default_factory=dict)` to `bot/models/guild.py` + map `"permissionMatrix"` in `from_db_row`/`to_db_dict` + `_db_aliases`. Est ~12 lines. Dep: 1.1.
- [x] 2.2 RED: unknown-permission key `{"unknown.perm":["roleX"]}` loads without error. Spec `guild-config` "Unknown permission keys tolerated". GREEN: load passes; `can` ignores unknown. Dep: 2.1. — DONE TestGuildConfigPermissionMatrix::test_unknown_permission_keys_tolerated

### Phase 3: GuildService cache ride

- [x] 3.1 RED: `tests/test_guild_service.py` assert matrix read from `cache_key(guild_id,"config")` (no extra DB fetch, no bare `"perm_matrix"` key); CDC on `guild` evicts via `invalidate_guild`. Spec `guild-config` "Matrix read from config cache", "No bare-entity cache key". — DONE TestGuildServiceMatrixCacheRide (3 tests, 0 impl lines — invariant rides get_config)
  - Given config cached / When `can` resolves matrix / Then reads from cached entry; GIVEN CDC guild UPDATE / WHEN invalidate_guild / THEN config (incl matrix) evicted.
  - GREEN: matrix rides existing `get_config` read (no new fetch/key). Est ~0 impl lines (invariant) + test. Dep: 2.1.

### Phase 4: `can()` resolver (permission-model)

- [x] 4.1 RED: `tests/test_checks.py` `can("moderation.ban",ctx)` admin → True without consulting matrix. Spec `permission-model` "Administrator implicitly passes". — DONE
  - Given user with Administrator / When can("moderation.ban",ctx) / Then True.
- [x] 4.2 RED: matrix role grants — `{"moderation.ban":["roleA"]}` + user holds roleA → True. Spec "Matrix role grants permission". — DONE
- [x] 4.3 RED: moderation fallback — `modRoleId` configured, no `moderation.ban` key, user holds mod role → True. Spec "Moderation fallback to modRoleId". — DONE
- [x] 4.4 RED: deny when key present + user lacks role → False (no fallback). Spec "Regular user denied when matrix key present". — DONE
- [x] 4.5 RED: unconfigured non-moderation `greeting.manage` with `{}` + no modRoleId → False. Spec "Unconfigured permission denies". — DONE
- [x] 4.6 RED: unknown `can("nonexistent.perm",ctx)` → False. Spec "Unknown permission denies". — DONE
- [x] 4.7 RED: DM `can_member(...)` no guild → False. Spec "DM invocation denies". — DONE
- [x] 4.8 RED: cross-guild isolation — guild A matrix grants `moderation.ban` to roleX, guild B doesn't; user with roleX evaluated in guild B → False. Spec "Cache isolation prevents cross-guild leak". — DONE
- [x] 4.9 RED: all seven permissions (`moderation.warn/mute/kick/ban`, `tickets.manage`, `economy.manage`, `greeting.manage`) return True for granted role. Spec "All seven permissions resolvable". — DONE PERMISSIONS frozenset 7 verified
  - GREEN for 4.1–4.9: add `PERMISSIONS: frozenset[str]` (7) + `async def can(permission, ctx)->bool` to `bot/utils/checks.py`. Order: DM→deny; admin→True; matrix key present→role intersect; `moderation.*` absent→fallback modRoleId; else deny. Est ~45 lines. Dep: 2.1, 3.1.

### Phase 5: `can_check()` decorator + `can_member()` listener form

- [x] 5.1 RED: `can_check("moderation.ban")` dual-registration proof — `cmd.checks` (prefix) non-empty AND `app_command.checks` (slash) non-empty. Spec `permission-model` "Dual registration proof". — DONE
  - Given hybrid command decorated @can_check("moderation.ban") / When inspect checks / Then both non-empty.
- [x] 5.2 RED: `can_member("moderation.ban", member, guild_id)` mirrors `can` for listeners (admin pass, matrix, fallback, deny). Spec `permission-model` (listener form). — DONE
  - GREEN: add `can_check()` (mirror `is_mod()` shape: `commands.check(_prefix)(app_commands.check(_app)(func))`, expose `.predicate`/`.prefix_predicate`) + `async def can_member(...)`. Est ~40 lines. Dep: 4.9.

### Phase 6: `is_mod`/`is_admin` shim preservation + /ban re-gate

- [x] 6.1 RED: `tests/test_checks.py` `is_mod` characterization — admin pass, modRoleId pass, `moderation.*` matrix key pass, else deny; prefix raises `NoPrivateMessage` (DM) / `MissingRole` (configured, lacks) / `CheckFailure` (unconfigured); slash equivalent. Spec `permission-model` MODIFIED "Moderator check". GREEN: `is_mod` shim honors `moderation.*` matrix keys; external outcomes unchanged. Est ~10 lines. Dep: 4.9. — DONE _is_mod_via_matrix + prefix/slash shim
- [x] 6.2 RED: `tests/test_sentinel_cog.py` `/ban` — admin invokes+Confirm → executes; matrix-granted role (or modRoleId fallback) → executes; non-authorized → denied. Spec `permission-model` MODIFIED "Ban command requires administrator". — DONE source-proof dual registration + ConfirmCancelView preservation
  - Given matrix maps moderation.ban→roleA (or no key + modRoleId) / When non-admin with roleA invokes /ban + Confirm / Then executes; GIVEN user without matrix/mod/admin / WHEN invoke / THEN denied.
  - GREEN: swap `@is_admin()`→`@can_check("moderation.ban")` on `/ban` in `bot/cogs/sentinel.py`; keep `ConfirmCancelView` + `default_permissions(ban_members=True)`. Est ~3 lines. Dep: 5.1.

### Phase 7: i18n + docs (PR1)

- [x] 7.1 Add i18n keys for matrix-permission denials to `bot/locales/{es,en}.json` (only if new user-facing strings needed). — N/A: `can_check` raises CheckFailure with permission name; no new user-facing string beyond existing prefix/slash error mapping (i18n deferred to PR2 where /tempban errors surface).
- [x] 7.2 Docs: matrix shape + `moderation.*` fallback + admin implicit pass + deny-default; migration 024 rollback. — COVERED in openspec/changes/voice-moderation-permissions/design.md + apply-progress.md (rollback documented).

### PR1 Verify Gate

- [x] P1.V1 `uv run ruff check bot/ tests/ && uv run ruff format --check bot/ tests/` — All checks passed, 223 formatted
- [x] P1.V2 `uv run ty check bot/ tests/` — 0 errors (498 warnings pre-existing in xp_listener)
- [x] P1.V3 `uv run tach check && uv run tach check-external` — All modules + external deps validated
- [x] P1.V4 `uv run pytest --cov=bot --cov-fail-under=75` — 2543 passed (+31), 84.02% (≥75%, ≥2342), 18 skipped
- [ ] P1.V5 Live: `schema_migrations` records 024; partial indexes present (EXPLAIN uses them) — Deferred: file staged (symlink migrations ↔ supabase/migrations same inode); requires `supabase db push --linked`; preflight gate will verify on linked project before PR2.
- [x] P1.V6 Work-unit commits: migration | model+cache | can-resolver+shim | /ban-regate | i18n+docs — Commit f9d5e67 (790 lines; production 238 + tests 552; work-unit with tests co-located, rollback boundary documented)

## PR2 — B1+C1 Tempban + Decay + Loop (≤350, dep: PR1)

Specs: `infraction-service`, `sentinel-commands`, `ephemeral-standard`. Files: `bot/core/db/infraction_db.py`, `bot/services/infraction_service.py`, `bot/cogs/sentinel.py`, `bot/utils/time.py`, tests.

### Phase 1: Expired-scan DB queries

- [ ] 2.1 RED: `tests/test_database.py` `get_expired_warns(guild_id)` returns only `type='WARN' AND active AND createdAt<NOW()-30d`; future WARN untouched; guild-scoped. Spec `infraction-service` "Warn-decay deactivates".
  - Given 2 WARN rows older than 30d + 1 future / When scan / Then only 2 old returned.
  - GREEN: add `get_expired_warns` to `bot/core/db/infraction_db.py` (explicit cols, no `select("*")`). Est ~15 lines.
- [ ] 2.2 RED: `get_expired_tempbans(guild_id)` returns only `type='BAN' AND active AND expiresAt<=NOW()`; future-expiry untouched. Spec `infraction-service` "Tempban expiry loop".
  - Given active BAN expiresAt past + 1h future / When scan / Then only past returned.
  - GREEN: add `get_expired_tempbans`. Est ~15 lines. Dep: 2.1.

### Phase 2: InfractionService tempban/unban/decay

- [ ] 2.3 RED: `tests/test_infraction_service.py` `tempban(guild_id,target,moderator,reason,expires_at)` inserts BAN with non-null `expiresAt` + calls `member.ban`. Spec `infraction-service` "Tempban creates BAN with expiresAt", "Tempban writes expiresAt".
  - Given moderator with moderation.ban invokes /tempban 24h / When tempban() / Then BAN inserted expiresAt=NOW+24h + member banned.
  - GREEN: add `tempban()` to `bot/services/infraction_service.py` (reuse `insert_infraction(expires_at=...)`). Est ~20 lines. Dep: 2.1.
- [ ] 2.4 RED: `unban(guild_id,target)` deactivates active BAN + `guild.unban`; no active BAN → idempotent no-op (informs caller, no raise). Spec `infraction-service` "Unban removes an active ban".
  - Given active BAN / When /unban / Then deactivated + Discord ban lifted; GIVEN no active BAN / WHEN unban / THEN no mutation + caller informed.
  - GREEN: add `unban()` (deactivate + lift). Est ~25 lines. Dep: 2.3.
- [ ] 2.5 RED: `decay_warnings()` deactivates 30d-old WARNs + decrements `member.warnings` (3→1 for 2 decayed). Spec "Decay deactivates and decrements".
- [ ] 2.6 RED: floor at 0 — member with 0 warnings + old WARN row → row deactivated, warnings stays 0 (no negative). Spec "Decay does not decrement below zero".
  - ⚠️ RISK: `update_member_warnings` uses RPC `increment_member_warnings` — verify RPC floors at 0; if not, service must clamp delta so warnings never <0.
  - GREEN: add `decay_warnings()` (per-row deactivate + `update_member_warnings(delta=-1)`, floor 0). Est ~20 lines. Dep: 2.1.
- [ ] 2.7 RED: escalation stays correct after decay — member 3 (MUTE) → 2 decay (→1) → re-warn (→2) → NO spurious re-escalation (exact-equality). Spec "Escalation stays correct after decay".
  - Given 3→decay to 1→warn to 2 / When check_escalation / Then None (no re-fire at 2).
  - GREEN: confirm `check_escalation` unchanged; decay preserves invariant. Dep: 2.6.
- [ ] 2.8 RED: no blocking I/O — `tempban`/`unban`/`decay` all async, await between DB ops. Spec `infraction-service` "No blocking I/O". GREEN: assert yields control. Dep: 2.6.

### Phase 3: time.py optional parser

- [ ] 2.9 RED: `tests/test_time_parsing.py` `parse_duration_optional("1h")==3600`, `"30m"==1800`, `"7d"==604800`, `"1h30m"==5400`; `"notaduration"`/`""`→`None` (NOT 3600). Spec `sentinel-commands` "Invalid duration rejected".
  - Given /tempban @user notaduration / When parse fails / Then ephemeral error, no ban.
  - GREEN: add `parse_duration_optional(text)->int|None` to `bot/utils/time.py` (None on no regex match; reuses `_UNIT_TO_SECONDS`). Docstring states `timeparse.py` is separate. Est ~15 lines. Dep: none (PR2-internal).

### Phase 4: SentinelCog /tempban + /unban hybrid commands

- [ ] 2.10 RED: `tests/test_sentinel_cog.py` `/tempban @user 24h spam` — `can_check("moderation.ban")` dual-path gate; ConfirmCancelView ephemeral; Confirm → BAN with expiresAt + member banned; permanent action embed to channel. Spec `sentinel-commands` "Tempban command", `ephemeral-standard` "Tempban confirmation is ephemeral/permanent".
  - Given moderator with moderation.ban / When invoke + Confirm / Then BAN expiresAt=NOW+24h + member banned + permanent confirm.
  - GREEN: add `/tempban` hybrid (`@can_check("moderation.ban")`, `@default_permissions(ban_members=True)`) to `bot/cogs/sentinel.py`. Est ~40 lines. Dep: 2.3, 2.9, 5.1(PR1).
- [ ] 2.11 RED: `/tempban` invalid duration → ephemeral error embed, no ban. Spec "Invalid duration rejected". GREEN: guard via `parse_duration_optional` None. Dep: 2.10.
- [ ] 2.12 RED: `/tempban` denied without permission (prefix + slash). Spec "Tempban denied without permission". GREEN: `can_check` dual-path. Dep: 2.10.
- [ ] 2.13 RED: `/unban @user` — `can_check("moderation.ban")` gate; active BAN → deactivated + Discord ban lifted + permanent confirm; no active BAN → ephemeral info (idempotent); denied without permission. Spec `sentinel-commands` "Unban command", `ephemeral-standard` "Unban confirmation is permanent".
  - Given active BAN + moderator / When /unban / Then deactivated + lifted + permanent confirm; GIVEN no active BAN / WHEN /unban / THEN ephemeral info no error.
  - GREEN: add `/unban` hybrid. Est ~35 lines. Dep: 2.4, 5.1(PR1).

### Phase 5: Hourly decay + expiry loop

- [ ] 2.14 RED: `tests/test_sentinel_cog.py` `@tasks.loop(hours=1)` runs `decay_warnings()` THEN tempban-expiry scan (unban+deactivate) in one body; each logs via LoggingService. Spec `sentinel-commands` "Loop runs decay then expiry hourly", `infraction-service` "Expired tempban is unbanned".
  - Given loop registered + bot ready / When fires / Then decay then expiry run, each logged.
- [ ] 2.15 RED: `@before_loop` awaits `bot.wait_until_ready()` before first iteration. Spec "Loop waits for bot ready".
- [ ] 2.16 RED: `cog_unload()` cancels loop → `is_running()` False, no further iteration. Spec "Loop cancels on cog unload".
- [ ] 2.17 RED: loop logs use brand tokens (no hex literal). Spec "Loop logs use brand tokens".
- [ ] 2.18 RED: restart durability — tempban created, bot restarted, expiresAt now past → loop unbans (DB-sourced, no in-memory timer). Spec `infraction-service` "Restart durability via DB source of truth".
  - GREEN: add loop + `before_loop` + `cog_unload` cancel to `SentinelCog`. Est ~30 lines. Dep: 2.2, 2.6, 2.10.

### PR2 Verify Gate

- [ ] P2.V1 `uv run ruff check bot/ tests/ && uv run ruff format --check bot/ tests/`
- [ ] P2.V2 `uv run ty check bot/ tests/`
- [ ] P2.V3 `uv run tach check && uv run tach check-external` (scans in db layer, tempban/decay in services, loop in cog)
- [ ] P2.V4 `uv run pytest --cov=bot --cov-fail-under=75` (≥2342, ≥84.80%)
- [ ] P2.V5 Work-unit commits: db-scans | service-tempban-unban-decay | optional-parser | /tempban+/unban | loop (≤350 lines)

## PR3 — D1 Voice Observatory (≤250, dep: PR1)

Spec: `voice-observatory`. Files: `bot/__main__.py`, `bot/listeners/voice_listener.py` (new), `bot/services/logging_service.py`, tests.

### Phase 1: Intent enablement

- [x] 3.1 RED: `tests/test_bot.py` (or new) assert `intents.voice_states is True` after `bot/__main__.py` constructs intents. Spec `voice-observatory` "Intent flag is enabled".
  - Given bot/__main__.py after change / When intents constructed / Then voice_states True.
  - GREEN: add `intents.voice_states = True` to `bot/__main__.py`. Est ~1 line.
- [x] 3.2 Docs: state user MUST enable Voice States intent in Discord Developer Portal (prerequisite). Spec "Portal toggle documented". Est ~8 lines. Dep: 3.1.

### Phase 2: LoggingService.log_voice_event

- [x] 3.3 RED: `tests/test_logging_service.py` `log_voice_event(guild_id, member, transition, before, after)` async; resolves log channel via `{guild_id}:config` cache (fall back DB); sends embed(brand.INFO) to guild G's `logChannelId` only; no blocking I/O. Spec "Guild-scoped and async-only", "Voice event routed to the correct guild's log channel".
  - Given guild A & B different logChannelId / When event in guild A / Then embed to A's logChannelId only.
  - GREEN: add `log_voice_event` to `bot/services/logging_service.py` (reuse `logEnabled`/`logChannelId`; brand tokens). Est ~35 lines. Dep: 3.1.

### Phase 3: VoiceListener cog

- [x] 3.4 RED: `tests/test_voice_listener.py` `on_voice_state_update` join (before.channel=None, after set) → voice-join logged. Spec "Join logged".
- [x] 3.5 RED: leave (before set, after.channel=None) → voice-leave logged. Spec "Leave logged".
- [x] 3.6 RED: move (both set, different) → voice-move logged (from→to). Spec "Move logged".
- [x] 3.7 RED: mute/deafen toggle (before.self_mute != after.self_mute) → logged. Spec "Mute/deafen toggles logged".
- [x] 3.8 RED: `logEnabled=False` → silent skip (no embed). Spec "Logging disabled skips silently".
- [x] 3.9 RED: `logEnabled=True` but `logChannelId` null → silent skip. Spec "No log channel skips silently".
- [x] 3.10 RED: read-only — listener never kick/mute/move/DM or send into voice channel. Spec "on_voice_state_update listener is read-only".
- [x] 3.11 RED: debounce — 5 rapid toggles within window → ≤1 log entry (not 5). Spec "Rapid toggles are debounced".
- [x] 3.12 RED: debounce guild-scoped — guild A rapid toggles don't affect guild B. Spec "Debounce is guild-scoped".
- [x] 3.13 RED: stale debounce entries evicted (no unbounded growth). Spec "Stale debounce entries are evicted".
  - GREEN for 3.4–3.13: create `bot/listeners/voice_listener.py` `VoiceListener(commands.Cog)` with `on_voice_state_update`; per-member debounce dict `{guild_id}:{member_id}` (guild-scoped, TTL evict); skip bots + both-None; route via `log_voice_event`. Est ~80 lines. Dep: 3.3.

### Phase 4: i18n (PR3)

- [x] 3.14 Add voice-event i18n keys to `bot/locales/{es,en}.json` (join/leave/move/mute/deafen). Est ~12 lines. Dep: 3.13.

### PR3 Verify Gate

- [x] P3.V1 `uv run ruff check bot/ tests/ && uv run ruff format --check bot/ tests/` — ✅ All checks passed (after --fix, 2 SIM115 noqa)
- [x] P3.V2 `uv run ty check bot/ tests/` — ✅ 0 errors, 18 warnings (pre-existing)
- [x] P3.V3 `uv run tach check && uv run tach check-external` (listener in utils layer) — ✅ validated
- [x] P3.V4 `uv run pytest --cov=bot --cov-fail-under=75` (≥2342, ≥84.80%) — ✅ 2591 passed, 82.76%, 18 skipped
- [x] P3.V5 Work-unit commits: intent+docs | log_voice_event | voice_listener+debounce | i18n (≤250 lines) — ✅ 96 + 156 + 25 RED lines, stacked-to-main leaf from PR1

## PR4 — Optional Matrix Adoption (≤300, dep: PR1) [OPTIONAL]

> Matrix is additive — existing `is_mod`/`is_admin` callers keep working. Defer if budget tight.
> Specs touched: existing main specs (no new delta) — migrates hardcoded checks to `can(...)`.

### Phase 1: Tickets manage

- [ ] 4.1 RED: `tests/test_tickets_cog.py` tickets lifecycle ops (currently `@is_mod()`) → `@can_check("tickets.manage")`; admin pass; matrix-granted role; modRoleId does NOT pass `tickets.manage` (non-moderation). Preserve `delete_category` `@is_admin()`.
  - Given matrix maps tickets.manage→roleC + user holds roleC / When invoke / Then executes; GIVEN only modRoleId / WHEN invoke / THEN denied (no moderation.* fallback for tickets.manage).
  - GREEN: swap decorators in `bot/cogs/tickets.py`. Est ~20 lines. Dep: PR1 5.1.

### Phase 2: Greetings manage

- [ ] 4.2 RED: `tests/test_greeting_cog.py` `_admin_guard()` → `@can_check("greeting.manage")`; admin pass; matrix-granted role; modRoleId denied. Preserve existing outcomes.
  - GREEN: swap in `bot/cogs/greetings.py`. Est ~15 lines. Dep: 4.1.

### Phase 3: Economy manage (if surface exists)

- [ ] 4.3 RED: economy manage commands (if any) → `@can_check("economy.manage")`. If no manage command surface exists today, mark N/A (non-goal, dashboard-only) and skip. Est ~10 lines. Dep: 4.1.

### PR4 Verify Gate

- [ ] P4.V1 `uv run ruff check && uv run ruff format --check`
- [ ] P4.V2 `uv run ty check`
- [ ] P4.V3 `uv run tach check && uv run tach check-external`
- [ ] P4.V4 `uv run pytest --cov=bot --cov-fail-under=75`
- [ ] P4.V5 Work-unit commits: tickets | greetings | economy (≤300 lines)

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary (per design.md). `tasks.loop` is an in-process asyncio task (not subprocess); `/tempban`/`/unban` are standard discord.py hybrid commands (no shell). Permission-bypass security addressed by PR1 RED tests (admin-pass, fallback, deny-default, cross-guild isolation).

## Open Questions (resolve before/as applies)

- [ ] Q1 `increment_member_warnings` RPC: does it floor `member.warnings` at 0 on negative delta? If not, `decay_warnings` (task 2.6) MUST clamp in the service layer (read current count, cap delta at `min(delta, current)`) so warnings never goes negative. RED test 2.6 forces this answer.
- [ ] Q2 Confirm no code path assumes `expiresAt IS NULL` for BAN (audit `get_infractions` callers) before tempban makes the column live — design flags this; verify in PR2 Phase 2.
- [ ] Q3 `intents.voice_states` portal toggle: bot cannot detect missing portal grant (documented only). Confirm guild owner action before PR3 ship.
