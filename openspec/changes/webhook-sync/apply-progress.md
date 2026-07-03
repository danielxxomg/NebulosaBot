# Apply Progress: Webhook Cache Sync — PR1 (bot-side slice)

**Change**: webhook-sync
**Artifact store**: openspec (+ engram topic `sdd/webhook-sync/apply-progress`)
**Mode**: Strict TDD
**Slice**: PR1 — bot-side only (Phases 1, 2, 3 + bot `.env.example` + aiohttp reconcile). Dashboard (Phase 4) is PR2.
**Status**: ✅ success — all PR1 tasks complete, all tests green, gates clean.

> This is the corrective re-run. The previous apply attempt returned an empty
> result and did NOT write this file, leaving partial work. This batch
> VERIFIED the partial work (Phases 1–2) and COMPLETED the missing pieces
> (Phase 3 bot wiring, `.env.example`, aiohttp reconcile). Nothing was redone.

## Completed Tasks (PR1)

- [x] 1.1 **BotConfig webhook fields** (`bot/config.py`, `tests/test_config.py`) — prior batch
- [x] 1.2 **WebhookSyncPayload** (`bot/webhook/models.py`, `tests/test_webhook_models.py`) — prior batch
- [x] 2.1 **HMAC verify** (`bot/webhook/auth.py`, `tests/test_webhook_auth.py`) — prior batch
- [x] 2.2 **Webhook endpoint** (`bot/webhook/server.py`, `tests/test_webhook_server.py`) — prior batch
- [x] 2.3 **Server lifecycle** (`bot/webhook/server.py`, `tests/test_webhook_server.py`) — implemented by prior batch, unmarked; verified GREEN this batch
- [x] 3.1 **setup_hook integration** (`bot/bot.py`, `tests/test_bot.py`) — **implemented this batch** (the gate failure)
- [x] 5.1 **Update .env.example** — **implemented this batch** (the gate failure)
- [x] 5.3 **Reconcile aiohttp** (`requirements.txt`) — **implemented this batch** (the gate failure)

## TDD Cycle Evidence (Strict TDD)

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.1 | `tests/test_config.py` | Unit | N/A (config) | ✅ Prior | ✅ 9/9 pass | ✅ defaults+override+invalid | ✅ Clean |
| 1.2 | `tests/test_webhook_models.py` | Unit | N/A (new) | ✅ Prior | ✅ 5/5 pass | ✅ valid+missing+malformed | ✅ Clean |
| 2.1 | `tests/test_webhook_auth.py` | Unit | N/A (new) | ✅ Prior | ✅ 9/9 pass | ✅ valid/missing/tampered/empty | ✅ Clean |
| 2.2 | `tests/test_webhook_server.py` (endpoint) | Integration | N/A (new) | ✅ Prior | ✅ 7/7 pass | ✅ 200/401/400/idempotent | ✅ Clean |
| 2.3 | `tests/test_webhook_server.py` (lifecycle) | Integration | N/A (new) | ✅ Prior | ✅ 5/5 pass | ✅ runner/None/port-conflict/stop | ✅ Clean |
| 3.1 | `tests/test_bot.py` | Unit+Integration | ✅ 2/2 pre-existing | ✅ Written first (6→7 failed) | ✅ 9/9 pass | ✅ start/stop/degraded/cache-None/close-order | ✅ ruff format |
| 5.1 | `.env.example` | Config | N/A | N/A (config file — TDD exception) | N/A | N/A | ✅ Clean |
| 5.3 | `requirements.txt` | Config | N/A | N/A (config file — TDD exception) | N/A | N/A | ✅ Clean |

**Task 3.1 TDD detail (this batch's primary work):**
- RED: Wrote 6 tests for `_start_webhook` / `_stop_webhook` / `close()` / `setup_hook` wiring. Ran them → 6 FAILED for the right reasons (`bot.bot` had no `start_webhook_server` import; `_start_webhook`/`_stop_webhook`/`close()` override absent; `setup_hook` did not call the server).
- GREEN: Added imports, `_webhook_runner` slot + init, `_start_webhook`, `_stop_webhook`, `close()` override, and the `await self._start_webhook()` call at the end of `setup_hook()`. Ran tests → all pass.
- TRIANGULATE: added a 7th test (`test_skips_when_cache_not_initialized`) to force the type-narrowing guard + prove the no-cache defensive path. RED→GREEN.
- REFACTOR: `uv run ruff format` (no behavior change); tests stayed green.

## Test Summary

- **Total tests**: 426 (419 baseline + 7 new bot-wiring tests)
- **Total tests passing**: 426
- **Total tests failing**: 0
- **Coverage**: 77.63% (threshold 70% ✅)
- **Layers used**: Unit (webhook auth/models/config/bot-wiring), Integration (webhook endpoint + server lifecycle via aiohttp TestClient)
- **Approval tests (refactoring)**: None — Phase 3 added new methods, did not refactor existing behavior.
- **Pure functions created**: `compute_signature`, `verify_signature`, `WebhookSyncPayload.from_json_bytes` (prior batch).

## Files Changed

| File | Action | What Was Done |
|------|--------|---------------|
| `bot/webhook/__init__.py` | Created (prior) | Package export for webhook helpers. |
| `bot/webhook/models.py` | Created (prior) | `WebhookSyncPayload` dataclass + `from_json_bytes`. |
| `bot/webhook/auth.py` | Created (prior) | HMAC-SHA256 `compute_signature`/`verify_signature` (constant-time). |
| `bot/webhook/server.py` | Created (prior) | `create_webhook_app`, `handle_sync`, `start_webhook_server`/`stop_webhook_server` (AppRunner/TCPSite, OSError→degraded). |
| `bot/config.py` | Modified (prior) | `webhook_secret`/`webhook_host`/`webhook_port` fields + `from_env` loading with safe defaults. |
| `bot/bot.py` | Modified (this batch) | Imported webhook server funcs; added `_webhook_runner` slot+init; `_start_webhook`/`_stop_webhook`; overrode `close()`; call `_start_webhook()` at end of `setup_hook()`. |
| `tests/test_webhook_auth.py` | Created (prior) | 9 HMAC tests. |
| `tests/test_webhook_models.py` | Created (prior) | 5 payload tests. |
| `tests/test_webhook_server.py` | Created (prior) | 12 endpoint + lifecycle tests; ruff-formatted this batch. |
| `tests/test_config.py` | Modified (prior) | +8 webhook config tests. |
| `tests/test_bot.py` | Modified (this batch) | +7 webhook lifecycle wiring tests (`_start_webhook`/`_stop_webhook`/`close()`/`setup_hook`). |
| `.env.example` | Modified (this batch) | Added `WEBHOOK_SECRET`/`WEBHOOK_HOST`/`WEBHOOK_PORT` with comments. |
| `requirements.txt` | Modified (this batch) | `aiohttp==3.9.5` → `3.14.1` to match `uv.lock` (transitive via discord.py 2.7.1). |
| `openspec/changes/webhook-sync/tasks.md` | Modified (this batch) | Marked 2.3, 3.1, 5.1, 5.3 `[x]`. |

## Verification Results

| Gate | Command | Result |
|------|---------|--------|
| Full suite + coverage | `uv run pytest` | ✅ 426 passed, 77.63% coverage |
| Lint (scoped) | `make lint` | ✅ All checks passed |
| Types (scoped) | `make type` | ✅ Success: no issues in 6 source files |
| Security | `make security` | ✅ Exit 0; 0 medium/high; 0 issues in webhook module |
| Webhook module types | `uv run mypy bot/webhook/` | ✅ no issues in 4 source files |
| Changed-file lint | `uv run ruff check <files>` | ✅ All checks passed |
| Changed-file format | `uv run ruff format --check <files>` | ✅ all formatted |
| `make ci` feasibility | lint+type+security+test+cov | ✅ all components pass |

## Deviations from Design

None — implementation matches `design.md`. The bot starts the webhook in
`setup_hook()` after cache/services/tree-sync (degraded-safe), stores the
`AppRunner` on `self._webhook_runner`, and tears it down in `close()` before
`super().close()`. `start_webhook_server` catches `OSError` + empty-secret and
returns `None` (degraded TTL-only mode), exactly per the Lifecycle/Failure
Modes section. The design's `guild_id: str` note vs. spec's integer `guild_id`
is resolved per the spec (integer; `invalidate_guild(str(payload.guild_id))`).

## Issues Found

- **Prior batch left Phase 3 unwired** (the gate failure): `bot/bot.py` never
  started the server nor overrode `close()`. Fixed this batch via TDD.
- **Prior batch left task 2.3 unmarked** in `tasks.md` despite being
  implemented + tested. Verified GREEN and marked `[x]`.
- **mypy `arg-type` on `self.cache`**: `_start_webhook` passed `TTLCache | None`
  to a `TTLCache` param. Resolved with a tested type-narrowing guard
  (`if self.cache is None: return`) — both type-safe and strict-TDD compliant.
- **`requirements.txt`/`uv.lock` drift**: aiohttp pinned `3.9.5` vs resolved
  `3.14.1`. Reconciled to `3.14.1` (transitive via discord.py 2.7.1; NOT added
  as a direct dependency). Note: `discord.py` itself is pinned `2.4.0` in
  requirements.txt vs `2.7.1` in uv.lock — pre-existing drift, OUT of this
  PR's scope (task 5.3 is aiohttp-only); flagged for a later reconcile pass.
- **6 LOW-severity bandit findings** exist in pre-existing `bot/` code (none in
  the webhook module; below the `--severity-level medium` gate). Pre-existing
  debt, not introduced here.

## Remaining Tasks (PR2 — dashboard)

- [ ] 4.1 Webhook helper (`dashboard/lib/webhook-sync.ts` + vitest)
- [ ] 4.2 Wire guild-actions → `sendWebhookSync(gid, "guild_config")`
- [ ] 4.3 Wire economy-actions → `sendWebhookSync(gid, "economy_config")`
- [ ] 4.4 Wire greeting-actions → `sendWebhookSync(gid, "greeting_config")`
- [ ] 5.2 Update `dashboard/.env.local.example` — `BOT_WEBHOOK_URL`, `WEBHOOK_SECRET`
- [ ] 6.1 Full suite incl. `cd dashboard && npx vitest run` (bot half done: 426 pass)

## Workload / PR Boundary

- **Mode**: chained PR slice — PR1 (bot-side), autonomous and verifiable on its own.
- **Current work unit**: PR1 — bot webhook module + lifecycle wiring + bot env + aiohttp.
- **Boundary**: starts at Phase 1 (config/models), ends at Phase 3 (bot wiring) +
  bot `.env.example` + aiohttp reconcile. Does NOT touch the dashboard (Phase 4 = PR2).
- **Chain strategy**: two-PR split — PR1 (bot, this batch) → PR2 (dashboard, next).
  PR1 is self-contained: the bot can run with/without the webhook (degraded-safe),
  so PR2 can land independently afterward.
- **Estimated review budget impact**: tracked diff 349 insertions / 22 deletions across
  8 files + 4 new webhook module files (264 lines) + 3 new test files (384 lines).
  Within the bot-side slice scope; no dashboard lines.

---

## Post-4R Fix (R4-C1 + W1 + double-log) — corrective TDD batch

**Trigger**: 4R review confirmed CRITICAL finding R4-C1 (corroborated by R1 + R3).
The webhook required `guild_id` as INT (`models.py` line 53) while the ENTIRE
bot uses STR guild_id (DB `guild.id TEXT`, services `get_config(guild_id: str)`,
cache keys `{guild_id}:config`). The dashboard reads guild_id from Supabase as
TEXT and sends `{"guild_id": "123"}` (string) -> bot returned 400 ->
`invalidate_guild` NEVER called -> cache stale 5min = the EXACT desync this
feature closes. The test suite locked in the bug
(`test_webhook_models.py::test_non_integer_guild_id_raises_value_error`
asserted a string guild_id raises).

**Mode**: Strict TDD (Red-Green-Refactor).

### Fixed this batch

- [x] **C1 — accept str guild_id, store as str** (`bot/webhook/models.py`,
      `tests/test_webhook_models.py`, `bot/webhook/server.py`). `from_json_bytes`
      now accepts `guild_id` as `str | int`, rejects JSON booleans (bool is an
      int subclass), and STORES/RETURNS `guild_id` as `str` (int coerced via
      `str()`). `WebhookSyncPayload.guild_id` type is now `str`. `server.py:59`
      `invalidate_guild(str(payload.guild_id))` -> `invalidate_guild(payload.guild_id)`
      (redundant `str()` removed; the model contract now guarantees str).
- [x] **W1 — reconcile `__init__.py` `__all__` with docstring** (`bot/webhook/__init__.py`).
      Re-exported `create_webhook_app`, `compute_signature`, `verify_signature`,
      `SIGNATURE_HEADER` from the submodules and added them to `__all__` (RUF022
      sorted). Verified NO import cycle: `auth`/`models` have no package-level
      imports; `server` imports submodules directly (`from bot.webhook.auth
      import ...`), not the package `__init__`. Import order auth -> models ->
      server so deps load before dependents.
- [x] **Double-log (R3-S3 / R2-S2)** (`bot/config.py:96`). Demoted the
      "WEBHOOK_SECRET not set" log from `logger.warning` to `logger.debug` so
      only `server.py:106`'s "webhook server not started" WARN remains as the
      single startup signal.
- [x] **Doc alignment** (`openspec/.../cache-sync-webhook/spec.md`). Requirement
      "Payload validation" + "Valid payload processed" scenario updated to say
      `guild_id` is a STRING (int accepted+coerced, bool rejected), matching
      `design.md:41,53` (already str) and the DB TEXT convention.

### TDD Cycle Evidence (Strict TDD)

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| C1 | `tests/test_webhook_models.py` | Unit | 34/34 pass (models+server+config) | 5 fail (string rejected; int not coerced to str) | 22/22 pass (models+server) | 4 cases (str-accept, int-coerce, str+entity, bool-reject) | ruff format + RUF022 fix |
| W1 | (no test — pure re-export) | N/A | import check OK | N/A (structural) | import + 37/37 pass | N/A | RUF022 sorted |
| double-log | `tests/test_config.py` | Unit | 15/15 pass | N/A (log level; no caplog assertion existed) | 15/15 pass | N/A | Clean |
| spec.md | (doc) | N/A | N/A | N/A | N/A | N/A | Clean |

**C1 TDD detail:**
- RED: rewrote `test_webhook_models.py` — replaced the bug-locking
  `test_non_integer_guild_id_raises_value_error` (asserted string raises) with
  `test_string_guild_id_accepted_as_str`; added `test_integer_guild_id_coerced_to_str`
  (triangulation, different int), `test_string_guild_id_with_entity_accepted`, and
  `test_boolean_guild_id_rejected` (bool still rejected); updated happy-path +
  dataclass tests to assert `guild_id == "12345"` (str). Ran -> 5 FAILED for the
  right reasons (current int-only code: string raised ValueError; int returned
  `12345` not `"12345"`).
- GREEN: `models.py` — `guild_id: str`; `from_json_bytes` rejects bool first,
  then accepts `str | int`, coerces via `str()`; removed redundant `str()` at
  `server.py:59`. Ran -> 22/22 pass (models + server).
- TRIANGULATE: 4 cases covering str-accept, int-coerce (different value
  `987654321`), str+entity end-to-end, and bool-rejection.
- REFACTOR: `ruff format` (no change) + `ruff check --fix` (RUF022 sorted
  `__all__`); tests stayed green.

### Verification Results (this batch)

| Gate | Command | Result |
|------|---------|--------|
| Full suite + coverage | `uv run pytest` | 429 passed (426 + 3 net new), 77.65% coverage |
| Lint (scoped) | `make lint` | All checks passed; 17 files formatted |
| Types (scoped) | `make type` | Success: no issues in 6 source files |
| Security | `make security` | Exit 0; 0 medium/high severity (6 high-confidence LOW-severity pre-existing, none in webhook module) |
| Webhook import cycle | `python -c "from bot.webhook import ..."` | OK — no cycle |
| `make ci` (lint+type+security+test+cov) | all components | all pass |

### Files Changed (this batch)

| File | Action | What Was Done |
|------|--------|---------------|
| `bot/webhook/models.py` | Modified | `guild_id: int` -> `str`; `from_json_bytes` accepts `str | int`, rejects bool, coerces to str; docstring updated. |
| `bot/webhook/server.py` | Modified | `invalidate_guild(str(payload.guild_id))` -> `invalidate_guild(payload.guild_id)` (redundant `str()` removed). |
| `bot/webhook/__init__.py` | Modified | Re-exported `create_webhook_app`, `compute_signature`, `verify_signature`, `SIGNATURE_HEADER`; added to `__all__` (RUF022 sorted). |
| `bot/config.py` | Modified | Demoted "WEBHOOK_SECRET not set" log from WARNING to DEBUG (eliminates double-log with `server.py:106`). |
| `tests/test_webhook_models.py` | Modified | Replaced bug-locking test with str-acceptance; +3 tests (str-accept, int-coerce, str+entity); bool-rejection; happy-path/dataclass updated to str. |
| `openspec/changes/webhook-sync/specs/cache-sync-webhook/spec.md` | Modified | Requirement + "Valid payload processed" scenario: `guild_id` is a STRING (int accepted+coerced, bool rejected). |

### Deviations from Design (correction)

**This batch REVERSED the prior deviation.** The earlier record said the
design's `guild_id: str` note vs. spec's integer `guild_id` was "resolved per
the spec (integer)". R4-C1 proved that resolution was the bug: the dashboard
sends a STRING guild_id (Supabase TEXT), so the int-only model returned 400 and
`invalidate_guild` was never called. The fix aligns to `design.md` (str), NOT
the old spec — and the spec was corrected to str in this batch. The
implementation now matches `design.md:41,53` exactly (`guild_id: str`). The
prior "Deviations from Design" note above is superseded by this correction.

### Issues Found

- The prior test suite LOCKED IN the R4-C1 bug
  (`test_non_integer_guild_id_raises_value_error` asserted a string raises).
  Replaced with a test that asserts strings are accepted. This is why the bug
  survived the first apply: the test green-barred the wrong contract.
- `invalidate_guild` is robust to both str and int (its prefix is built via
  f-string `{guild_id}:`), so the server tests passed both before and after the
  fix — the desync only manifested with real dashboard traffic sending strings.

### Workload / PR Boundary

- **Mode**: corrective fix on the PR1 (bot-side) slice — no new PR scope added.
- **Boundary**: bot-side only; dashboard (PR2) untouched. All changes are within
  the existing PR1 diff (webhook module + config + tests + spec).
- **Estimated review budget impact**: small additive delta on the PR1 diff
  (models.py coercion logic, 3 net new tests, init re-export, 1 log-level line,
  spec wording). Well within the single-PR review budget.

### Status

Post-4R fix complete. 429/429 tests green; lint/type/security clean; coverage
77.65%. **Ready for commit/push/PR1** (deferred per instructions — left in
working tree, NOT committed).

