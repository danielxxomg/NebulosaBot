# Tasks: clean-1.0 — Everything Clean Before v1.0.0

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~4450 total across 9 PRs |
| 400-line budget risk | High (overall); per-PR all ≤1500 |
| Chained PRs recommended | Yes (9 stacked PRs, pre-approved) |
| Suggested split | S0 → S1 → S2a → S2b → S3 → S4 → S5 → S6A → S6B |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| S0 | Stability/security fixes (tempban, zombie audit, error handler, token log, cache eviction, gate flips) | PR 1 | `uv run pytest tests/test_tempban_serialization.py tests/test_zombie_autoclose_audit.py tests/test_error_handler_branches.py tests/test_cache_eviction.py` | N/A — mocked Discord/PostgREST builders | Revert merge commit; DDL none |
| S1 | Transcript triple-path + private bucket | PR 2 | `uv run pytest tests/test_transcript_triple_path.py` | N/A — mocked Storage/DM/channel | Revert; bucket migration idempotent |
| S2a | /setup panel framework + Tickets module | PR 3 | `uv run pytest tests/test_setup_panel.py tests/test_setup_module_tickets.py tests/test_i18n_key_coverage.py` | Bot boot in test guild opens /setup panel | Revert; no DB schema change |
| S2b | Welcome/Goodbye/Log/Language modules + delete legacy greeting groups | PR 4 | `uv run pytest tests/test_setup_module_welcome.py tests/test_setup_module_goodbye.py` | Bot boot: test-button preview to configured channel | Revert; legacy cogs restored by revert |
| S3 | pg_cron retention + crash_report + index hygiene + storage purge | PR 5 | `uv run pytest tests/test_storage_purge_mechanism.py tests/test_retention_purge.py tests/test_crash_report.py tests/test_migrations.py` | `cron.unschedule` then revert; DDL idempotent | Revert after `cron.unschedule`; DDL additive |
| S4 | config.toml tomllib loader + RotatingFileHandler | PR 6 | `uv run pytest tests/test_operational_config.py tests/test_rotating_file_handler.py` | Boot with config.toml present/absent | Revert; absent-file fallback preserved |
| S5 | Hygiene/debt (CDC parity, PLC0415, dead i18n, dedup, governance, CI pins) | PR 7 | `uv run pytest tests/test_cache_cdc_parity.py tests/test_i18n_no_dead_keys.py tests/test_close_ticket_dedup.py` | N/A — static analysis + unit | Revert; pure refactor/deletion |
| S6A | Migrate sentinel/tickets/utility/core hybrids → app_commands; delete /sync; help slash-only | PR 8 | `uv run pytest tests/test_zero_hybrid_guard.py tests/test_help_slash_only.py` | Bot boot: slash tree renders /command only | Revert; hybrids restored |
| S6B | Migrate ocio/economy/stellar/greetings; /dados→/dice; flip /8ball+/banana+/dice permanent; AGENTS.md ocio para same unit | PR 9 | `uv run pytest tests/test_ocio_commands.py tests/test_dice_rename.py tests/test_ocio_permanence.py` | Bot boot: /dice /8ball /banana permanent, cooldown ephemeral | Revert; ephemeral-exception restored |

> Archive-safety note: every MODIFIED delta carries the FULL requirement text (unchanged scenarios preserved) so `sdd-archive` merges deltas without losing scenario coverage. Apply must not trim MODIFIED blocks.

## Phase S0: Stability & Security (PR 1, ~450 lines)

- [x] S0.1 RED: `tests/test_tempban_serialization.py` — assert outgoing query string contains `expiresAt=not.is.null` and no `neq.null` (real postgrest builder, no fake masks). Ref: data-retention "Tempban expiry query serialization".
- [x] S0.2 Fix `bot/core/db/infraction_db.py:199` → `builder.not_.is_("expiresAt", "null")`; delete `neq(None)`. Verify scenario "Expired tempban deactivates without serialization error".
- [x] S0.3 RED: `tests/test_zombie_autoclose_audit.py` — sweep-closed zombie writes `zombie_autoclose` row (actorId=system, applied reason); channel-delete path same row; audit-insert failure → ticket stays closed + WARNING logged + nothing propagates. Ref: ticket-service "Zombie auto-close writes an audit entry".
- [x] S0.4 Add `_audit_zombie_autoclose(guild_id, ticket_id, outcome, reason)` on `bot/services/ticket_lifecycle_service.py`; wire at repair seam (`ticket_repair_service.py`) + lifecycle seam; relax strict `audit_persisted` to best-effort ONLY for automated zombie case (actorId=system ∧ reason startswith `zombie:`); manual repairs keep strict contract. (D6)
- [x] S0.5 RED: `tests/test_error_handler_branches.py` — CheckFailure/MissingPermissions → ephemeral localized reply (names missing perm); no-DM branch; unexpected error title+message via `t()` in guild language; guild_id extracted from interaction. Ref: bot-core "Global error handler".
- [x] S0.6 Implement branches in `bot/bot.py` `on_app_command_error`/`on_command_error`; remove any DM-first fallback; route titles via `t()`. Ref: ephemeral-standard "Slash-only error visibility".
- [x] S0.7 RED: `tests/test_token_never_logged.py` — capture all log records at DEBUG; assert no token substring at any level. Ref: operational-config "Token never logged at any level".
- [x] S0.8 Remove token-fragment INFO line at `bot/config.py:279`.
- [x] S0.9 RED: `tests/test_cache_eviction.py` — on_guild_remove evicts all `{G}:*`; other guilds unaffected; post-eviction read misses. Ref: cache-layer "Eviction on guild remove".
- [x] S0.10 Wire `on_guild_remove` → `invalidate_guild(guild_id)` in `bot/bot.py` using `bot/core/cache.py` existing helper.
- [x] S0.11 Ticket-timer `unix=` kwarg fix (transfer-to-self UI pre-validation + log ERROR→WARNING); `/rank` cooldown + shared semaphore; cache/semaphore eviction quick wins. (proposal S0 misc)
- [x] S0.12 Gate flips: betterleaks blocking ON; coverage floor 80; GGA hook includes `tests/`. (proposal S0)
- [x] S0.13 `,` invariant grep guard: add/run guard confirming no diff touches `TicketsCog.on_message` `,` close-timer parsing. (tickets-touching unit)

## Phase S1: Transcript Triple-Path (PR 2, ~350 lines)

- [x] S1.1 RED: `tests/test_transcript_triple_path.py` — each branch fails alone, others succeed; DM-closed → Storage+log succeed; log-channel-missing → DM+Storage succeed, no error; `transcriptUrl` stores PATH not CDN URL. Ref: transcript-service "Triple-path transcript delivery" + "Log-channel-missing behavior preserved".
- [x] S1.2 Create `migrations/027_private_transcript_bucket.sql` — `INSERT INTO storage.buckets ('transcripts', public=false) ON CONFLICT` (idempotent). (Required by S1 Storage path before S3.)
- [x] S1.3 Extend `bot/services/transcript_service.py` with `deliver()` orchestrator: bytes once → fresh `discord.File` per path; DM creator (fail→log, continue); Storage upload PRIVATE `transcripts/{guildId}/{ticketId}/{filename}` (fail→log, continue); log channel (existing `upload()`). (D2)
- [x] S1.4 Wire `bot/services/ticket_repair_service.py._close_single_ticket` to call `deliver()`; set `transcriptUrl` = Storage object PATH (not CDN URL).
- [x] S1.5 `,` invariant grep guard (tickets-touching unit — repair service touches ticket close).

## Phase S2a: /setup Panel Framework + Tickets Module (PR 3, ~800 lines)

- [x] S2a.1 RED: `tests/test_setup_panel.py` — one non-ephemeral message; nav edits same message (no duplicate); 🗑 deletes; restart routes via static custom_id; interaction_check denials ephemeral; admin implicit pass; non-admin blocked by default_perms. Ref: setup-panel "Persistent non-ephemeral panel" + "Authorization without new matrix key".
- [x] S2a.2 RED: `tests/test_setup_panel_nav.py` — breadcrumb reflects selection; refresh shows live state (post-mutation re-read). Ref: setup-panel "Module navigation with breadcrumb and refresh".
- [x] S2a.3 RED: `tests/test_permission_matrix_unchanged.py` — `PERMISSIONS` frozenset == exactly 7 keys, no setup key; `tickets.manage` gates Tickets-module mutation; `greeting.manage` denies Welcome save when absent. Ref: permission-model "Setup surface reuses existing matrix keys".
- [x] S2a.4 Create `bot/views/setup_panel.py`: `SetupPanelView(ui.View, timeout=None)`; static custom_ids `setup:nav`/`setup:refresh`/`setup:close`/`setup:{module}:{action}`; register via `bot.add_view()` in `NebulosaBot.setup_hook`; breadcrumb in embed footer token `nbpanel|module=<key>`; render recomputes from services cache-first. (D1)
- [x] S2a.5 Define `SetupModule` protocol (`key`, `permission_key`, `render`, `components`, `handle`); `MODULES` registry dict. (D1)
- [x] S2a.6 Implement `interaction_check`: admin OR `can_member()` matrix grant; denial → ephemeral error, no mutation.
- [x] S2a.7 RED: `tests/test_setup_module_tickets.py` — guided create-category (resolved IDs), delete-category confirmed, list-categories; custom-fields editor builds structure (no typed JSON/UUID). Ref: setup-panel "Guided editors only".
- [x] S2a.8 Create `bot/views/setup_modules/tickets.py` (Tickets module): create/delete/list categories + custom-fields editor via Selects/buttons/modals over concrete Discord objects; absorb category/field management from raw-UUID commands. (D1, setup-wizard MODIFIED)
- [x] S2a.9 Modify `bot/cogs/setup.py`: hybrid → pure `@app_commands.command()` `/setup`, zero params, `default_permissions(administrator=True)`, opens panel. Ref: setup-wizard "Setup command".
- [x] S2a.10 i18n: add keys under `setup.panel.*` and `setup.module.tickets.*` to `bot/locales/es.json` + `en.json` (symmetric). Ref: setup-panel "Internationalization".
- [x] S2a.11 `,` invariant grep guard (tickets-touching unit — Tickets module touches categories).

## Phase S2b: Welcome/Goodbye/Log/Language Modules + Legacy Group Deletion (PR 4, ~500 lines)

- [ ] S2b.1 RED: `tests/test_setup_module_welcome.py` — module save matches legacy effect (channel updated + cache invalidated); test button delivers REAL localized preview to configured channel; preview failure (no channel) → ephemeral error, no mutation. Ref: welcome-goodbye "Setup-module configuration parity and preview".
- [ ] S2b.2 RED: `tests/test_setup_module_goodbye.py` — same parity + preview for goodbye.
- [ ] S2b.3 Create `bot/views/setup_modules/welcome.py`, `goodbye.py`, `log.py`, `language.py`; register in `MODULES` without framework edits. (D1)
- [ ] S2b.4 Expose orphan columns (`cardEnabled`, `themeId`, `onboardingChannelId`) in Welcome module editors.
- [ ] S2b.5 Implement test-button action `setup:{module}:test`: defer → render REAL artifact via `GreetingService` (identical path to join/leave) → deliver to configured channel → edit panel with outcome; missing/inaccessible channel → ephemeral followup error. (D1 preview mechanics)
- [ ] S2b.6 Verify greeting card text via caller (title + member-count from `t()`), no hardcoded copy. Ref: welcome-goodbye "Localized greeting card text".
- [ ] S2b.7 i18n: add `setup.module.welcome/goodbye/log/language.*` keys to es/en symmetric. Ref: setup-panel i18n.
- [ ] S2b.8 Delete `/welcome` + `/goodbye` command groups and `*_test` commands in `bot/cogs/greetings.py` AFTER parity verified. (delete-before-migrate: deletions precede S6 migration of survivors). Ref: welcome-goodbye REMOVED.

## Phase S3: Retention Engine (PR 5, ~400 lines)

- [ ] S3.1 **PRE-S3 BLOCKER**: Pin storage-purge mechanism. RED `tests/test_storage_purge_mechanism.py` asserting chosen mechanism deletes `storage.objects` rows AND handles orphaned backing files (reconciliation sweep OR pg_net Storage API delete endpoint). Document decision in design follow-up. **S3.2+ cannot start until this lands.** (design Open Question mandate)
- [ ] S3.2 Implement pinned storage-purge (SQL DELETE on `storage.objects` + orphan reconciliation, OR pg_net API path) per S3.1 decision.
- [ ] S3.3 RED: `tests/test_retention_purge.py` — old closed ticket + 3 notes purged; sub-tickets deleted BEFORE parents (observable statement order); recent closed ticket kept; stale mute >180d purged; permanent BAN >180d retained. Ref: data-retention "Ticket retention" + "Infraction retention".
- [ ] S3.4 Create `migrations/028_retention.sql`: `retention_setting(key PK, days)` seeded (tickets 30 / infractions 180 / crash 30); ticket purge fn (collect expired parents+subs → DELETE `ticket_note` → DELETE sub-tickets → DELETE parents, RESTRICT-order mandatory); infraction purge fn (`DELETE WHERE NOT (type='BAN' AND "expiresAt" IS NULL) AND COALESCE("expiresAt","createdAt") < now()-ttl`); `cron.schedule` jobs. DDL `IF NOT EXISTS` / `DO $guard$`. (D3, delete-before-migrate ordering: purge before parent deletes)
- [ ] S3.5 RED: `tests/test_crash_report.py` — unhandled exception → exactly one `crash_report` row; business ERROR → no row; rows >30d purged, newer retained. Ref: data-retention "Crash report scope and TTL".
- [ ] S3.6 Create `bot/services/crash_report_service.py` `CrashReportService.record()` called ONLY from unhandled branches of `on_app_command_error`/`on_command_error` + root-level CRITICAL logging handler. (F4 scope)
- [ ] S3.7 Create `migrations/029_crash_report_indexes.sql`: `crash_report(id, guildId NULLABLE, command, traceback, createdAt)`; crash purge cron; `CREATE INDEX IF NOT EXISTS idx_member_updated_at ON member("updatedAt")`; `DROP INDEX IF EXISTS idx_ticket_note_created`. Idempotent re-run safe. Ref: data-retention "Index hygiene".
- [ ] S3.8 Wire `NebulosaBot.setup_hook` retention upsert from `OperationalConfig.retention` at boot; cron reconcile (flag off → `cron.unschedule`).

## Phase S4: Operational Config (PR 6, ~350 lines)

- [ ] S4.1 RED: `tests/test_operational_config.py` — valid file applies typed values; absent file → env-only boot (no error); malformed → `TOMLDecodeError` fail-fast naming parse failure; secrets-scan (no token/DB creds in config.toml); unknown keys → WARNING + ignored. Ref: operational-config "Typed TOML loader".
- [ ] S4.2 RED: `tests/test_rotating_file_handler.py` — rollover at 10MB; ≤5 backups; oldest pruned beyond fifth. Ref: operational-config "RotatingFileHandler bounds disk usage".
- [ ] S4.3 Create `bot/operational_config.py`: frozen dataclass tree (`LoggingSettings`, `LimitSettings`, `TimeoutSettings`, `RetentionSettings`, `FeatureFlags` → `OperationalConfig`); `tomllib` parse at boot; precedence built-in defaults ← config.toml; `.env` does NOT feed operational settings. (D4)
- [ ] S4.4 Create `config.toml` + `config.example.toml` (defaults, no secrets).
- [ ] S4.5 Modify `bot/__main__.py:20` bootstrap: `RotatingFileHandler(maxBytes=10*1024*1024, backupCount=5)` replaces `basicConfig` file sink; load `OperationalConfig` at boot. (D4)
- [ ] S4.6 Feature-flag read API: `cfg.flags.retention_enabled` consumed by setup_hook cron reconcile.

## Phase S5: Hygiene & Debt (PR 7, ~400 lines)

- [ ] S5.1 RED: `tests/test_cache_cdc_parity.py` — documented set == `frozenset(SUBSCRIBED_TABLES)` both directions; member/economy under explicit `Deferred:` marker; drift fails. Ref: cache-layer "Documentation matches CDC reality".
- [ ] S5.2 Add machine-parseable claims block to `bot/core/cache.py` docstring; source of truth = `SUBSCRIBED_TABLES` (`bot/core/realtime.py:49`). (D7)
- [ ] S5.3 RED: `tests/test_i18n_no_dead_keys.py` — literal `t()` key inventory + dynamic-prefix whitelist (runtime-built families); green only after purge; es/en symmetric; `test_i18n_key_coverage.py` stays green. (D7)
- [ ] S5.4 Prune dead i18n keys in `bot/locales/{es,en}.json` symmetrically until S5.3 passes.
- [ ] S5.5 Enable `PLC0415` in `pyproject.toml` ruff select; lift ~25 function-level imports to module top; survivors carry inline `# noqa: PLC0415 -- <cycle-break | optional-dependency probe | facade>` (3 AGENTS.md-allowed categories only). (D7)
- [ ] S5.6 Extract `TicketLifecycleService._finalize_close(...)` (dual-branch dedup: guild-scoped fast path vs pre-read fallback); behavior-identical (denied/success audit, zombie-aware channel-discard skip, `_clear_scheduled_fields`); host D6 audit post-S5. Existing close suite stays green. (D7)
- [ ] S5.7 Delete `governance_guard.py` + `tests/test_product_artifact_audit_governance.py`; verify no residual importer via full pytest run. (D7)
- [ ] S5.8 Scope `.betterleaks.toml` env-family allowlists with explicit `rules=` constraints; drop test_live_catalog synthetic-URI entry if cleanup removes them. (D7)
- [ ] S5.9 Pin `.github/workflows/code-quality.yml:57-66` osv-scanner v2.5.1 / betterleaks v1.8.1 by release-artifact SHA256 (`sha256sum -c -`); checksums committed next to workflow. (D7)
- [ ] S5.10 Route `bot/services/rank_renderer.py` hardcoded card strings through `t()`; cleanup `tests/test_live_catalog.py` dead fixtures; i18n coverage suite green. (D7)
- [ ] S5.11 MODIFIED delta archive-safety check: confirm all MODIFIED delta specs retain full requirement text (unchanged scenarios) for `sdd-archive` merge safety.

## Phase S6A: Hybrid→app_commands PR-A (PR 8, ~500-600 lines)

- [ ] S6A.1 RED: `tests/test_zero_hybrid_guard.py` — grep asserts ZERO `hybrid_command`/`hybrid_group` declarations remain across `bot/cogs/**` after this PR (scoped to S6A-touched archetypes). Ref: bot-core "Zero hybrid declarations remain".
- [ ] S6A.2 RED: `tests/test_help_slash_only.py` — help renders `/command` entries only, no prefix examples. Ref: bot-core "Help shows slash syntax only".
- [ ] S6A.3 Delete `/sync` command in `bot/cogs/core.py` (delete-before-migrate: deletion precedes survivor migration). Ref: core-commands REMOVED.
- [ ] S6A.4 Migrate sentinel/tickets/ticket_*_flow/utility/core hybrids → `@app_commands.command()` per D5 recipe (`@app_commands.describe` + `locale_str`, `interaction.response.send_message`/`followup`, `Literal`→`choices`, `@commands.cooldown`→`@app_commands.checks.cooldown`).
- [ ] S6A.5 Migrate `/help` (`bot/cogs/core.py:190`) to pure app command enumerating app-command tree, `/command` syntax only. (D5)
- [ ] S6A.6 `,` invariant grep guard + close-confirmation suite green (tickets-touching unit — tickets/ticket_*_flow cogs).

## Phase S6B: Hybrid→app_commands PR-B + Ocio Visibility Flip (PR 9, ~500-600 lines)

- [ ] S6B.1 RED: `tests/test_dice_rename.py` — `/dice` resolves in default locale; `/dados` does NOT; es `name_localizations` "dados", en "dice"; range [1,sides], reject <2/>100. Ref: ocio-commands "Dice command".
- [ ] S6B.2 RED: `tests/test_ocio_permanence.py` — `/8ball`+`/banana`+`/dice` replies PERMANENT; zero DB writes (no insert/update/delete); 20 localized `ocio.8ball.*` responses; title from `ocio.8ball.embed_title` (no raw key); banana pool 5-8 webp + dorada 1%@30cm + Pillow fallback. Ref: ocio-commands banana/8ball + ephemeral-standard "Fun commands permanent standard".
- [ ] S6B.3 RED: `tests/test_ocio_cooldown.py` — `CommandOnCooldown` handler replies ephemerally with localized `retry_after`; releases after 5s. Ref: ocio-commands "Ocio commands cooldown and handler".
- [ ] S6B.4 Migrate ocio/economy/stellar/greetings survivors → pure app_commands per D5 recipe (deletions of /welcome+/goodbye groups already done in S2b).
- [ ] S6B.5 Rename `/dados`→`/dice` with `name_localizations={es:"dados"}`; migrate to `@app_commands.command`.
- [ ] S6B.6 Flip `/8ball`, `/banana`, `/dice` to permanent visibility; keep `@commands.cooldown(1,5,BucketType.user)`; ensure zero DB writes (ocio path). Add ephemeral `CommandOnCooldown` branch in `on_app_command_error` (localized retry_after). (D5)
- [ ] S6B.7 Update `AGENTS.md` ocio-exception paragraph (remove the `/banana`/`/8ball` ephemeral exception) IN THE SAME WORK UNIT/COMMIT as the S6B.6 visibility flip. (D5 doc coupling)
- [ ] S6B.8 Delete remaining legacy greeting command declarations (survivors not deleted in S2b). (delete-before-migrate honored)
- [ ] S6B.9 Full zero-hybrid grep guard across entire `bot/cogs/**` green; close-confirmation suite green; `,` listener untouched (explicit rule: no diff touches `TicketsCog.on_message`).
