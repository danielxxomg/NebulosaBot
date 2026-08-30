# Design: clean-1.0 — Everything Clean Before v1.0.0

## Technical Approach

Nine stacked PRs (S0, S1, S2a, S2b, S3, S4, S5, S6A, S6B) implementing the approved proposal. Design answers HOW per locked decisions: no new matrix key, global-only retention, non-ephemeral panel, restart-only config. All specs in `specs/` are satisfied as written; deltas carry full requirement text (archive-safe).

## Architecture Decisions

### D1 — /setup panel framework (`setup-panel`, `setup-wizard`)

| Option | Tradeoff | Decision |
|---|---|---|
| One static `ui.View` + breadcrumb parsing | Spec-literal but fragile state | Rejected |
| **Static-id namespace + message-embedded module token** | Restart-safe, no DB state | **Chosen** |

- `bot/views/setup_panel.py`: `SetupPanelView(ui.View)` with `timeout=None`; static custom_ids `setup:nav` (Select), `setup:refresh`, `setup:close`, and per-module actions `setup:{module}:{action}` (e.g. `setup:tickets:create_category`) — all literal strings registered via `bot.add_view(SetupPanelView(...))` in `NebulosaBot.setup_hook` next to the ticket views.
- Lifecycle: `/setup` (pure app command, zero params, `default_permissions(administrator=True)`) posts ONE non-ephemeral message; every interaction calls `interaction.response.edit_message()` on that same message; 🗑 deletes it. Pending values are never stored — each render recomputes from services (cache-first), so Refresh re-reads live state.
- Breadcrumb encoding: human breadcrumb in embed author line + machine token in embed footer `nbpanel|module=<key>` parsed by refresh/nav to know what to re-render. Survives restarts because it lives in the message itself.
- Module registry: `SetupModule` protocol — `key`, `permission_key: str | None`, `render(guild_id) -> Embed`, `components(guild_id) -> list[Item]`, `handle(interaction, action) -> None`. Registry `MODULES: dict[str, SetupModule]`; S2a ships framework + tickets module, S2b registers welcome/goodbye/log/language without framework edits.
- Permission enforcement points: command gate = Discord default perms (admins implicit pass, no matrix consult); component interactions bypass slash checks, so `SetupPanelView.interaction_check` re-authorizes every action — admin OR existing matrix grant via `can_member()` (`tickets.manage` / `greeting.manage`); denial = ephemeral error, nothing mutates.
- i18n: keys under `setup.panel.*` and `setup.module.<key>.*`; covered by `tests/test_i18n_key_coverage.py`.
- Preview mechanics (welcome-goodbye): test buttons are ordinary module actions — custom_id `setup:{module}:test` routed through the SAME `handle(interaction, "test")` contract; the module defers, renders the REAL artifact via `GreetingService` (identical path to join/leave delivery) and delivers it to the configured channel, then edits the panel with the outcome. Missing/inaccessible channel → ephemeral followup error; config is never mutated by a preview.

### D2 — Transcript triple-path (`transcript-service`)

Extend `TranscriptService` with a delivery orchestrator invoked from `TicketRepairService._close_single_ticket` (current generate→upload→DB site):

```
generate() ─┬→ DM creator (user.send(file))            [fail→log, continue]
            ├→ Storage upload PRIVATE bucket path       [fail→log, continue]
            │    transcripts/{guildId}/{ticketId}/{filename}
            └→ log channel (existing upload())          [unchanged behavior]
```

- Bytes generated once; fresh `discord.File` per path (a File's buffer is single-send).
- Private bucket `transcripts` created in migration (`INSERT INTO storage.buckets ... public=false`). Signed URLs rejected: they rot in ≤7d. **`transcriptUrl` semantics change**: stores the durable object PATH (not CDN URL); content recovery = DM copy or log-channel post; on-demand signed URL is future work.
- Each branch wrapped independently; DM failure (creator DMs closed) and Storage failure never abort close or remaining paths. Missing log channel skips only path 3 (preserved).

### D3 — Retention engine (`data-retention`)

Migration follows `migrations/012_ticket_audit.sql` pattern exactly (`DO $guard$ IF NOT EXISTS cron.job → cron.schedule(name, expr, $$fn$$)`).

- Configurable TTLs without runtime reads: migration creates `retention_setting(key TEXT PK, days INT)` seeded (tickets 30 / infractions 180 / crash 30); `NebulosaBot.setup_hook` upserts from `OperationalConfig.retention` at boot (restart-only). Cron jobs call SQL functions reading this table. Precedence documented: config.toml > SQL defaults; env NEVER feeds retention (locked F2).
- Ticket purge ordering inside one function (observable): 1) collect expired parents+subs (`status='closed' AND "closedAt" < now()-ttl`); 2) DELETE `ticket_note` for those ids; 3) DELETE sub-tickets (`"parentId" IS NOT NULL`); 4) DELETE parents (parentId FK is RESTRICT — order is mandatory).
- Infractions: `DELETE WHERE NOT (type='BAN' AND "expiresAt" IS NULL) AND COALESCE("expiresAt","createdAt") < now()-ttl`.
- `crash_report(id, guildId NULLABLE, command, traceback, createdAt)`. Single writer `CrashReportService.record()` called ONLY from: unhandled branches of `on_app_command_error` / `on_command_error`, plus a root-level CRITICAL logging handler routing to same service (F4 scope). Business ERROR logs never reach it (threshold CRITICAL; explicit call sites enumerated).
- Index hygiene: `CREATE INDEX IF NOT EXISTS idx_member_updated_at ON member("updatedAt")`; `DROP INDEX IF EXISTS idx_ticket_note_created`.

### D4 — operational-config (`operational-config`)

- New `bot/operational_config.py`: frozen dataclass tree (`LoggingSettings`, `LimitSettings`, `TimeoutSettings`, `RetentionSettings`, `FeatureFlags` → `OperationalConfig`), parsed by `tomllib` at boot.
- Precedence (explicit): built-in defaults ← `config.toml`; `.env` does NOT feed operational settings (env keeps only secrets/guild data via `BotConfig`). Absent file → defaults, boot proceeds (env-only behavior preserved). Malformed file → `TOMLDecodeError` propagates = fail-fast startup error naming the parse failure. Unknown keys log WARNING and are ignored (forward-compat).
- `RotatingFileHandler(maxBytes=10*1024*1024, backupCount=5)` replaces `basicConfig` file sink in `bot/__main__.py:20` bootstrap.
- Feature-flag read API: plain attribute access `cfg.flags.retention_enabled`; consumed by setup_hook cron reconcile + callers.

### D5 — S6 hybrid→app_commands migration

Recipe per archetype: `@commands.hybrid_command` → `@app_commands.command`; docstring params → `@app_commands.describe` + `locale_str`; `ctx.send(embed=..., ephemeral=e)` → `interaction.response.send_message(..., ephemeral=e)` (or `followup.send` after defer); `Literal` params → `app_commands.choices`; `@commands.cooldown` → `@app_commands.checks.cooldown` + new ephemeral `CommandOnCooldown` branch in `on_app_command_error` (localized retry_after — required by ocio spec).
Split plan: **PR-A** sentinel/tickets/ticket_*_flow/utility/core (delete `/sync`) ; **PR-B** ocio/economy/stellar/greetings + rename `/dados`→`/dice` (`name_localizations es:"dados"`) + flip `/8ball`,`/banana`,`/dice` permanent + delete legacy groups. `,` listener safety: zero-hybrid grep guard test + existing close-confirmation tests must stay green + explicit task rule "no diff may touch `TicketsCog.on_message`".
Doc coupling: AGENTS.md ocio-exception paragraph edit ships in the SAME work unit/commit as the visibility flip (apply-time doc change; GGA reviews them together).
Help: `/help` (`bot/cogs/core.py:190`) migrates to pure app command and enumerates the app-command tree rendering `/command` syntax only — no prefix examples (satisfies bot-core "help shows slash syntax only").

### D6 — Zombie autoclose audit (`ticket-service`)

Detection+close components already exist; only audit emission is new:

| Automatic path | Detection+close site | Close reason |
|---|---|---|
| Integrity sweep | `TicketRepairService.sweep_integrity` → `repair_ticket_from_evidence` (single seam) | `zombie:sweep` |
| Channel-delete repair | `TicketRepairService.handle_channel_delete` → same seam | `zombie:channel_deleted` |
| Scheduled-close loop | `TicketsCog` loop → `TicketLifecycleService.close_ticket` | `zombie:*` |

- Audit insert lives in ONE service method: `_audit_zombie_autoclose(guild_id, ticket_id, outcome, reason)` on `TicketLifecycleService` (repair service already composes lifecycle — dependency direction holds). Both seams call it after a successful automated zombie transition; wrapped in try/except → WARNING log, never raises: **audit failure never blocks or rolls back the close**.
- Action semantics: automated zombie closures write `action="zombie_autoclose"` with the applied close reason verbatim. In the repair seam this REPLACES the generic `"repair"` row when `actor_id=="system"` ∧ reason starts with `zombie:` — and for that automated case the current strict `audit_persisted` hard-fail (outcome=error) is relaxed to best-effort per spec; manual repairs keep the strict contract unchanged. In the lifecycle seam, `is_zombie` closes write `zombie_autoclose` instead of the generic `"close"` row.
- Actor id convention: literal `"system"` (matches existing repair-service default and `_audit_denied(..., "system")`).
- Ordering vs S5: S0 inserts the call at both branches; S5's `_finalize_close` extraction then carries it into a single site.

### D7 — S5 hygiene slice (`cache-layer` sync + debt)

- **CDC docs↔handler parity**: single source of truth = `SUBSCRIBED_TABLES` (`bot/core/realtime.py:49`, drives handler registration at :384). `bot/core/cache.py` module docstring gains a machine-parseable claim block (`Realtime-invalidated entities: ...`). New `tests/test_cache_cdc_parity.py`: documented set == `frozenset(SUBSCRIBED_TABLES)` in BOTH directions; any member/economy mention must sit under an explicit `Deferred:` marker, never under active claims.
- **PLC0415 sweep**: enable `PLC0415` in ruff select; lift ~25 function-level imports to module top; genuine survivors carry inline `# noqa: PLC0415 -- <cycle-break | optional-dependency probe | facade>` per the three AGENTS.md-allowed categories only.
- **Dead i18n purge**: reference inventory = literal `t()` keys across `bot/**` PLUS dynamic-prefix whitelist (runtime-built families, e.g. `setup.module.*`, `tickets.integrity.*`). Shipped as permanent `tests/test_i18n_no_dead_keys.py`; the purge lands by making it pass; es/en pruned symmetrically; `test_i18n_key_coverage.py` stays green.
- **close_ticket dual-branch dedup**: extract duplicated post-transition body of `TicketLifecycleService.close_ticket` (guild-scoped fast path vs pre-read fallback) into private `_finalize_close(...)` — behavior-identical (denied/success audit rows, zombie-aware channel-discard skip, `_clear_scheduled_fields`); hosts the D6 audit post-S5.
- **governance_guard.py deletion**: delete root `governance_guard.py` + its sole importer `tests/test_product_artifact_audit_governance.py`; archived openspec reports stay untouched (historical record); full pytest run proves no residual importer; coverage floor unaffected (pure deletion).
- **`.betterleaks.toml` scoping**: env-family path allowlists gain explicit `rules=` constraints so silences apply only to triaged rule classes (e.g. `generic-credential-uri`) — the S0 blocking flip must not mask unknown secret types in those paths. If test_live_catalog cleanup removes its synthetic URIs, drop that allowlist entry entirely.
- **CI binary SHA pins**: `.github/workflows/code-quality.yml:57-66` downloads osv-scanner v2.5.1 / betterleaks v1.8.1 by tag → pin by release-artifact SHA256 (`sha256sum -c -` verification step); checksums committed next to the workflow; existing `uses:` action pins unchanged.
- **rank_renderer t() routing + test_live_catalog cleanup** (`bot/services/rank_renderer.py`, `tests/test_live_catalog.py`): hardcoded card strings route through `t(guild_id, ...)`; dead fixtures trimmed.

## Data Flow

```
/admin /setup ─→ SetupPanelView(interaction_check: admin ∨ matrix key)
                     │ edit_message (same msg, footer token)
                     ├→ GuildService/GreetingService/TicketCategoryDB (cache-first)
                     └─→ save → cache.invalidate → re-render

ticket close → RepairService._close_single_ticket
                     └→ TranscriptService.deliver ─┬→ DM creator
                                                   ├→ Storage(private)/30d
                                                   └→ log channel
pg_cron daily ─→ purge fns ← retention_setting ← OperationalConfig (boot upsert)

auto zombie close (sweep ∨ channel-delete ∨ scheduled)
     └→ service seam → best-effort ticket_audit(zombie_autoclose, actorId=system)
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `bot/views/setup_panel.py` | Create | Persistent view, module registry protocol, render/close/refresh |
| `bot/views/setup_modules/*.py` | Create | Tickets (S2a); welcome/goodbye/log/language (S2b) |
| `bot/cogs/setup.py` | Modify | Hybrid → pure `/setup`, zero params, opens panel |
| `bot/cogs/greetings.py` | Modify→shrink | Delete `/welcome`//goodbye groups + `*_test` after parity |
| `bot/services/transcript_service.py` | Modify | Triple-path deliver, storage upload |
| `bot/services/ticket_repair_service.py` | Modify | Call triple-path; pass storage client |
| `bot/services/crash_report_service.py` | Create | crash_report writer |
| `bot/bot.py` | Modify | add_view panel, error-handler branches (CheckFailure/MissingPermissions, cooldown, t() titles, no-DM), crash hooks, on_guild_remove eviction, retention upsert, config load |
| `bot/core/db/infraction_db.py` | Modify | `not_.is_("expiresAt", "null")` replacing neq(None) |
| `bot/core/cache.py` | Modify | Eviction already exists (`invalidate_guild`) — wire only |
| `bot/config.py` | Modify | Remove token INFO line (279) |
| `bot/__main__.py` | Modify | RotatingFileHandler + OperationalConfig load |
| `bot/operational_config.py` | Create | Typed tomllib loader |
| `migrations/027_*.sql`…`029_*.sql` | Create | Retention fns+jobs, crash_report, indexes, bucket |
| `config.toml` + `config.example.toml` | Create | Defaults, no secrets |
| `AGENTS.md` | Modify | ocio exception paragraph removed (same unit as flip) |
| cogs S6: `sentinel/utility/core/ocio/economy/stellar/tickets/*flow` | Modify | Hybrid→app_commands |
| `bot/services/ticket_repair_service.py` | Modify (S0) | Best-effort `zombie_autoclose` audit in shared seam; relax strict persistence only for automated zombie case |
| `bot/services/ticket_lifecycle_service.py` | Modify (S0+S5) | `_audit_zombie_autoclose` helper + `_finalize_close` dual-branch dedup extraction |
| `tests/test_zombie_autoclose_audit.py` | Create (S0) | Sweep/channel-delete audited; audit failure never blocks close |
| `bot/core/cache.py` | Modify (S5) | Docstring claims block — CDC parity source of truth for docs side |
| `tests/test_cache_cdc_parity.py` | Create (S5) | Documented streams == `SUBSCRIBED_TABLES`, both directions; deferred labels enforced |
| `tests/test_i18n_no_dead_keys.py` | Create (S5) | Dynamic-key-safe dead-key detector (literal refs + prefix whitelist) |
| `bot/locales/{es,en}.json` | Modify (S5) | Dead key purge, symmetric |
| `pyproject.toml` + ~25 `bot/**/*.py` sites | Modify (S5) | Enable PLC0415; lift function-level imports; documented exceptions inline |
| `bot/services/rank_renderer.py` | Modify (S5) | Hardcoded strings → `t()` routing |
| `tests/test_live_catalog.py` | Modify (S5) | Dead fixture cleanup (may shrink betterleaks allowlist) |
| `governance_guard.py`, `tests/test_product_artifact_audit_governance.py` | Delete (S5) | Obsolete one-cycle governance guard + sole importer |
| `.betterleaks.toml` | Modify (S5) | Rule-scoped env allowlists |
| `.github/workflows/code-quality.yml` | Modify (S5) | osv-scanner/betterleaks downloads pinned by artifact SHA256 |

## Interfaces / Contracts

```python
class SetupModule(Protocol):
    key: str; permission_key: str | None
    def render(self, guild_id: str) -> discord.Embed: ...
    def components(self, guild_id: str) -> list[discord.ui.Item]: ...
    async def handle(self, interaction: discord.Interaction, action: str) -> None: ...

async def deliver(self, *, bytes_out: bytes, filename: str, creator: discord.abc.User,
                  guild_id: str, ticket_id: str,
                  log_channel: discord.TextChannel | None) -> TranscriptDeliveryResult

@dataclass(frozen=True) class OperationalConfig:
    logging: LoggingSettings; limits: LimitSettings
    timeouts: TimeoutSettings; retention: RetentionSettings; flags: FeatureFlags
```

Tempban fix: `builder.not_.is_("expiresAt", "null")` (postgrest-py v2 API) — wire format asserted by test.

## Testing Strategy

Strict TDD RED→GREEN per work unit; pytest + mocked Member/Interaction/Guild.

| Slice | Key tests |
|---|---|
| S0 | Real postgrest builder query-string assertion (`expiresAt=not.is.null` present, no `neq.null`); purge order assertion (notes→subs→parents statement order); eviction hit/miss/other-guild-unaffected; token-absence capture test over all levels; CheckFailure/MissingPermissions ephemeral replies; zombie autoclose: sweep-closed zombie writes `zombie_autoclose` row (actorId=system, applied reason), channel-delete path writes the same row, audit-insert failure → ticket stays closed + WARNING logged + nothing propagates to the sweep loop |
| S1 | Triple-path independence (each branch fails alone; others succeed); private-bucket metadata; transcriptUrl=path not URL |
| S2a/b | Same-message edit identity; restart routing (static ids); interaction_check denials ephemeral; matrix-grant success paths; guided flows persist resolved ids; i18n coverage; test-button preview delivered to real channel / ephemeral-safe failure |
| S3/S4 | Loader: valid/absent/malformed/secrets-scan tmp_path fixtures; rollover ≤5 backups; cron reconcile flag off→unschedule |
| S5 | CDC parity drift fails both directions + deferred labels asserted; dead-key detector green post-purge; `_finalize_close` dedup keeps denied/success/zombie-skip semantics (existing close suite green); governance modules gone (import probe); betterleaks config parses with rule-scoped allowlists; workflows assert `sha256sum -c` binary verification steps; rank_renderer keys covered by i18n coverage suite |
| S6 | Zero-hybrid grep guard; `/dice` localizations; permanence + zero-DB-write asserts; cooldown ephemeral branch; `,` listener untouched (close-confirmation suite green); help renders `/command` entries only |

## Threat Matrix

N/A — no routing tables, shell/subprocess execution, VCS/PR automation code, executable-file classification, or OS process integration changes. Discord component authorization is handled by D1's interaction_check design.

## Migration / Rollout

Each slice = one stacked PR; revert merge commit individually. S3 DDL idempotent; disable via `cron.unschedule` before revert. S4 falls back to env-only when `config.toml` absent.

## Open Questions

- [ ] Storage object purge mechanism — **NOT left to verify phase**. sdd-tasks MUST pin the mechanism as an explicit pre-S3 task with its own RED test: choose SQL `DELETE` on `storage.objects` vs pg_net fetch of the Storage API delete endpoint. Direct SQL risks orphaned backing files (metadata row deleted, object remains) — the pinned design MUST state how orphans are handled (reconciliation sweep, or prefer the pg_net API path). S3 implementation is blocked until this task lands.
