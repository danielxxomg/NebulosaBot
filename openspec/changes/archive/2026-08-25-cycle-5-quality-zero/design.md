# Design: Cycle 5 — Quality Zero (v1.0 readiness)

## Technical Approach

Nine stacked-to-main slices (S0–S7), ≤800 authored lines each, each slice = one PR boundary with its own verification gate: `uv run pytest && uv run ruff check bot/ tests/ && uv run ty check bot/ tests/`, plus betterleaks (staged) always, and jscpd + `uv lock --check` + full pytest at minimum on **S0/S3/S5/S6/S7** boundaries (mirrors `prek.toml` push-stage gates). Behavior changes follow strict TDD RED→GREEN. All anchors below were verified against current source.

## Architecture Decisions

### D1 — S1 ty-gate strategy (batch order + suppression policy)

| Batch | Rule | Count | Mode |
|---|---|---|---|
| B0 | `unused-type-ignore` | 155 | Mechanical deletion commit (no behavior risk; `unused-ignore-comment="error"` already global) |
| B1 | `invalid-argument-type` | 185 | File clusters, typed fixes / targeted casts |
| B2 | `unresolved-attribute` | 114 | Mostly mock typing → conftest factories (D8) unblock |
| B3 | `invalid-assignment` (26) + `not-subscriptable` (15) | 41 | Cluster tail |

Current state: ~15 `[[tool.ty.overrides]]` blocks in `pyproject.toml` (from `tests/test_audit_listener.py` onward) downgrade every rule to `"warn"` per file — these are the real debt. Each fixed cluster REMOVES its override block so global severity applies. Suppression policy: inline `# ty: ignore[<rule>]` ONLY with a written rationale comment on the same line (existing precedent: `bot/bot.py:222` cairosvg probe, `bot.py:641`). NO `[tool.ty.rules]` global ignores, NO new blanket overrides. Gate activation is the LAST S1 commit: add `[tool.ty.terminal] error-on-warning=true`; enforcement already exists at both layers (`prek.toml` `ty` hook priority=30, `.github/workflows/ci.yml:46`). Rollback: revert of the final commit alone restores warning-tolerant ty.

### D2 — S2 slash-policy shape

- **Prefix resolver**: replace `_build_prefix_callable` (`bot/bot.py:66-88`) with a module-level `async def _noop_prefix(bot_ref, message) -> list[str]: return []` keeping the `(bot, message) -> list[str]` signature discord.py expects; passed as `command_prefix` at `bot.py:164-167`. Closure over guild_service dies; `get_context` prefetch (`bot.py:358-366`) stays harmless (config still used by `/status`).
- **on_command_error** (`bot.py:415-493`): simplified body KEEPS the silent-ignore tuple `(CommandNotFound, DisabledCommand)` (defensive, zero-cost once inert) and both deferral guards (local handler `hasattr(ctx.command,"on_error")`; scoped `CommandOnCooldown` cog deferral). DELETES the DM-first branch (`L469-487`) and DM path (`L490-493`) per `bot-core` delta scenario "No DM-first branch"; retains log-first + single channel-path embed via `t(guild_id,...)`.
- **Help cleanup**: `_resolve_prefix` (`core.py:264-268`) callers at `core.py:170` (single-module) and `core.py:347` (paged builder): drop the `prefix` parameter from `_build_cog_help_embed`; all entries render `/command` syntax only. `core.py:119` status field stops interpolating `prefix=config.prefix` into `core.status.guild_config_loaded` (key text updated in both locales). AGENTS.md L17/18/22/23 rewritten in the same commit as the code they describe.

### D3 — S3 quality T1 details

- **LoggingService i18n**: 28 keys ×2 locales, naming `log.<domain>.<part>` following the existing orphaned `voice.*` precedent (e.g. `log.moderation.title`, `log.voice.join_title`). `log_moderation_action` (`logging_service.py:224-256`) swaps literals `"🛡️ Moderation"`, `"Target"`, `"Moderator"`, `"Reason"` → `t(guild_id, ...)`; `log_voice_event` wires the 10 orphan keys with `{mention}/{channel}/{from}/{to}/{state}` substitution. Coverage enforced by `tests/test_i18n_key_coverage.py` + AST scanner extension.
- **InfractionService.mute/kick/ban**: signatures mirror `tempban` (`infraction_service.py:152-174`) — `async def ban(self, guild_id, target_id, moderator_id, reason) -> Infraction` with `expires_at=None` passed to the shared `insert_infraction`; `mute(..., expires_at: str | None = None)`; `kick` identical to ban minus expiry. Service performs NO Discord action; SentinelCog keeps `timeout()/kick()/ban()` + caller-side `log_moderation_action` swap.
- **Audit-path asymmetry — RESOLVED: intentional, document it.** Mute/kick/ban audit caller-side exactly like tempban/unban (see sentinel.py:1227-1236 unban precedent); `apply_escalation` (`infraction_service.py:302,363`) audits service-side because it is a system-initiated flow with no cog caller. Rationale: minimal diff, consistent public API, exactly-one-audit invariant holds per flow (spec scenario satisfied). Docstring on each new method states which side owns auditing.
- **Migration 025**: DROP TABLE IF EXISTS `public.ticket_backup_categoryid_text_20260818` (destructive, approved in grill; recovery = DB dump only). Push live → 25/25.
- xp_listener role-rewards delegates to EconomyService method; audit_listener ticket-close routing goes through `TicketService` with an honest docstring (site: `audit_listener.py:136-170` channel-delete → coordinator delegation pattern; no state mutation in listener).

### D4 — S4 robustness/perf patterns

- **Raid guard: guild-scoped semaphore + drop-log. CHOSEN over time-window debounce.** Raids are join *bursts*: a debounce window silently swallows legitimate distinct greetings, while `asyncio.Semaphore(2)` per guild (dict keyed `guild_id`) caps concurrent Pillow renders, preserves them, and gives deterministic backpressure: non-blocking `acquire()`; on failure skip + `logger.warning("greeting dropped: raid saturation guild=%s")`. Lives in `GreetingService.dispatch_greeting`.
- **`,`-timer debounce**: dict keyed `f"{guild}:{channel}:{user}"`, 15s TTL, `_evict_stale(now)` — direct mirror of `voice_listener.py:47-57` (`_debounce: dict[str,float]`). Placed in `TicketsCog.on_message` (`tickets.py:230-265`) before `_dispatch_timer_message`.
- **economy_config cache**: `EconomyService.get_economy_config` (`economy_service.py:338-344`) becomes cache-first: `cache_key(gid, "economy_config")`, TTL re-exported as `ECONOMY_CONFIG_TTL = DEFAULT_TTL` in `bot/core/cache.py` (mirrors `GREETING_CONFIG_TTL`); invalidated in the config save path (mirror `greeting_service.save_config:97-105`). Hot paths `gain_xp:123` / `claim_daily:188` hit cache.
- **Resource-log task**: CoreCog `@tasks.loop(minutes=5)` (~20ln): logs `resource.getrusage(RUSAGE_SELF).ru_maxrss`, `cache.size`, `len(guilds)`; `before_loop → wait_until_ready()`, `cog_unload → cancel()` (AGENTS.md background-loop rules).
- Transcript: `_build_html` call (`transcript_service.py:95`) wrapped `await asyncio.to_thread(self._build_html, ...)` (method at `:135` stays sync-pure). Brand token dedup (`TRANSCRIPT_*`, `CARD_BG_*`, `LEGACY_BLURPLE`, `MUTED_TEXT` → `brand.py`); imgur footer icon dropped.

### D5 — S5a ImageService removal checklist (ordered)

1. `GreetingService.__init__` compat (`greeting_service.py:47-64`: `image_service` param + `_image_service` alias) — RED test first asserting protocol-only constructor.
2. `resolve_renderer` step-2 branch (`:130-134`, `generate_greeting_card` fallback) — resolver raises `AttributeError` unless `.render` exists.
3. `dispatch_greeting` TypeError fallback chain (`:210-263`) + `# noqa: C901` — direct single `to_thread(render_fn, ...)` call.
4. `bot.py` wiring: import `:28`, attr `:150`, instantiation `:217-218` (RankRenderer at `:238` STAYS — cog already uses `bot.rank_renderer`).
5. Delete `bot/services/image_service.py` shim + `tests/test_image_service.py`, `tests/test_image_service_no_mock.py`.
6. Drop rank byte-identity tests that only proved shim delegation (keep renderer-behavior tests); update mocks patching ImageService in `test_stellar_*`, greetings/greeting_service test files.
Verification: `vulture` advisory-clean, `rg "ImageService|image_service" bot/ tests/` → zero refs.

### D6 — S5b/c consolidation protocol

Per-cluster workflow: identify behavioral twin (diff assertions, not names) → parametrize or delete → focused `uv run pytest -k <cluster>` → full suite at slice end. Twin rule: nothing deleted without a confirmed surviving assertion covering the behavior; mock-theater call-asserts replaced by embed-content asserts BEFORE removal. conftest factory API hoist (~700ln):

```python
def make_ctx(*, guild_id="1", author=None, send=True, spec=...) -> NebulosaContext: ...
def make_member(*, roles=(), admin=False, **kw) -> discord.Member: ...
```

KEEP-list (protected guards, never deleted): `test_pr3_voice_listener_red.py` (read-only-listener greps), s3d1 guardrails tests, config hygiene tests (`test_ephemeral_standard`, `test_i18n_key_coverage`, `test_migrations`, `test_ruff_config`, `test_ci_config`).

### D7 — S6 CDC implementation order + updatedAt decision

Hard order (spec-verifiable in history):
1. **Hooks first**: every RPC/table mutator gains `if self._on_write is not None: await self._on_write(table, guild_id)` — `update_member_xp/coins/daily` (`economy_db.py:48-166`), `upsert_economy_config` (`:34-46`, table=`economy_config`), `update_member_warnings` (`member_db.py:36-58`). Hook plumbing already exists (`DatabaseBase._on_write` wired to `mark_recent_write` at `bot.py:310-311`) — mutators simply never call it.
2. **Migration 026** (publication): DO-block `ALTER PUBLICATION supabase_realtime ADD TABLE member, economy_config` catching SQLSTATE 42710 — verbatim `007_realtime_publication.sql:18` pattern. **Numbering: 025 = backup DROP (S3), 026 = publication (S6)** — matches free slots after current 024.
   **updatedAt: ADD NOW, both tables.** Rationale: incremental poll (`"updatedAt" > $last_check`) avoids full-scan invalidation storms on active guilds; trigger-maintained (migration `020_greeting_updated_at` precedent); one idempotent DDL, backward compatible, and adding it later means a second live-push dependency. Spec marks columns optional — we exercise the incremental path as primary, full-scan as tested fallback.
3. `realtime.py`: `SUBSCRIBED_TABLES` += 2 (`:49-54`); `_extract_guild_id` cases (`:109-126`) map both via `str(record["guildId"])`, DELETE falls back to `old_record["guildId"]`; watchdog counter increments at top of `_handle_cdc` (RECEIVED semantics); poll gains incremental branches.
4. Tests: `tests/test_realtime.py` — extract/echo-skip/poll/watchdog scenarios.

    DB write ──→ RPC mutator ──→ _on_write mark ──→ Supabase ──→ CDC echo ──→ RecentWriteSet skip
                                       (BEFORE publication ALTER lands — hard order)

### D8 — S7 convergence ops

Review range `v0.9.0-debt-zero..HEAD` via temporary env swap: `PR_BASE_BRANCH=v0.9.0-debt-zero bash .gga` … restore original value immediately after (documented in the slice task; never committed). Max 2 rounds. Isolated fixes land as their own commits; re-review base = parent commit of the isolated fix (not range start) to avoid re-reviewing converged slices. Residual-debt §1 (ty) + §7 closed with evidence links; gap register updated; archive last.

## Slice → PR mapping

| Slice | PR focus | Est. lines | Boundary gate (beyond base) |
|---|---|---|---|
| S0 | versions→0.9.0, hygiene-test parametrize, PEP 503, CHANGELOG | ~150 | jscpd, uv-lock, betterleaks |
| S1 | ty batches B0-B3 + gate commit last | ~700 | jscpd, uv-lock |
| S2 | prefix noop, error handler, help, AGENTS/specs, 8 KEEP-ADAPTED tests | ~600 | full pytest+ruff+ty |
| S3 | i18n 28×2 keys, infraction methods+swaps, 025 DROP+push | ~750 | jscpd, uv-lock |
| S4 | to_thread, semaphore, debounce, cache, resource-loop, brand dedup | ~500 | full pytest+ruff+ty |
| S5a | ImageService removal | ~400 (net −775) | jscpd, uv-lock |
| S5b/c | test consolidation | net −3300 | jscpd, uv-lock, vulture advisory |
| S6 | hooks→026→realtime→tests (ordered commits) | ~350 | jscpd, uv-lock |
| S7 | review ops + debt closure + archive | ~100 docs | full stack |

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit (RED→GREEN) | prefix inertness, error-handler no-DM, mute/kick/ban persistence, cache-first economy_config, debounce/semaphore, `_extract_guild_id`, echo suppression | Mock Member/Guild/Interaction; fake builders per existing test style |
| Integration | moderation end-to-end single-audit; CDC echo-storm ordering (hook-before-ALTER asserted from commit history); greeting burst under semaphore | `tests/integration/` patterns |
| Gates | every boundary: pytest+ruff+ty; S-named: jscpd/uv-lock/betterleaks; S1 final: `ty check` exit 0 fatal | CI parity (`ci.yml`) |

## Threat Matrix

| Row | Status | Reason / expected behavior / RED test |
|---|---|---|
| Shell/env manipulation (`.gga` `PR_BASE_BRANCH` swap, D8) | **Applicable** | Swap scoped to single invocation, restored in same task step; RED test: grep tasks forbid committed export |
| VCS/PR automation (stacked-chain retarget) | **Applicable** | Manual git ops only; child diffs must show no previous slices (rebase until clean) |
| Routing / subprocess / exec-file classification / process integration beyond above | N/A | No new routes, subprocesses, or executable-classification logic in this change |

## Migration / Rollout

- **S1**: gate commit is last → single-commit revert restores tolerant ty.
- **025**: destructive-but-approved; table disposable per grill ruling; recovery only via DB dump; documented in PR body.
- **026**: idempotent DO-block (re-runnable); reversible by removing tables from publication.
- **S5b/c**: twin-rule is the rollback — any deleted test lacking a confirmed twin is restored before merge; embed-content asserts land first.
- Each slice = one stacked PR; reverting it restores prior green state.

## Open Questions

- [ ] Confirm `log_voice_event` current literal inventory during apply (28-key table finalized against `logging_service.py` at implementation time).
- [ ] `updatedAt` trigger choice: reuse moddatetime extension vs custom trigger (decide at S6 apply; 020 precedent favors custom trigger).
