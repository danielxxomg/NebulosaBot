# Proposal: ticket-physical-split S3 — Physical Decomposition behind Facades

## Intent

Decompose ticket monolith (2,108 svc / 1,079 cog / 1,011 views) behind facades. Ordered DDL for FK integrity, close guild gaps, prove live parity (`sb_secret_`, RLS/FK/publication/migration) without mocks. Refs: `Diagramas/DiagramaSecuencia.mmd`, `DiagramaEntidad-Relacion.mmd`, `Ecosistema-Comandos.mmd`.

## Scope

### In Scope
- **6 stacked PRs → 4 slices** (`stacked-to-main`, `auto-chain`, ≤800): S3.1 guardrails 450–700, S3.2 FK/parity 550–800, S3.3 service 2× (A query/lifecycle, B repair/channel), S3.4 cog/views 2× (A cog, B views).
- **Ordered DDL**: preflight (21/21 UUID, 0 note orphans, audit 1/1) → `categoryId TEXT→UUID USING cast` → indexes → FKs → validate → drop dupe.
- **FK (Q1)**: `parentId→ticket.id RESTRICT`+depth1, `categoryId→category.id SET NULL`, `note.ticketId CASCADE`, `audit.ticketId SET NULL` + retention.
- **Index (Q2)**: drop `idx_ticket_guild_number` (shadowed, 0 scans); keep `idx_ticket_channel`; defer rest.
- **Creds (Q4)**: `sb_secret_` via RLS probe (`guild`/`ticket`); catalog via DB/RPC staging; PyJWT legacy only.
- **Guild+lint**: close `tickets.py:568,685,722` + 14 `db` refs; fix 11 `scripts/` Ruff.

### Out of Scope
Full domain/app/infra beyond facade; RLS policies; economy CDC; dashboard auth; extra index drops.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `ticket-service`: facade → `TicketLifecycle/Query/RepairService`, single `evaluate_repair_eligibility`.
- `ticket-commands`/`ticket-views`: split cog + views, preserve registration/IDs.
- `database-layer`: FK/cast + guild entries + preflight/parity.
- `live-schema-verifier`: `sb_secret_` probe + catalog parity.
- `permission-model`: recalc `is_mod` (25 decorators) + revalidation.

## Approach

Facade composition; `TicketService`/`TicketsCog`/views stable (`GuildService` pattern). No PR mixes DDL+move+lint.

- **S3.1 Guardrails**: recalc ledger, close guild callers, `sb_secret_` probe + catalog path, 11 Ruff fixes; gates `pytest`/`mypy`/`ruff`.
- **S3.2 Parity/DDL**: read-only preflights, additive FK+cast, reconcile 17 vs 19 migrations, lock/rollback evidence.
- **S3.3 Service**: A query/cache+lifecycle, B repair/integrity+channel/transcript; one cache/audit owner.
- **S3.4 Cog/Views**: A cog modules (admin/lifecycle/notes/integrity) + `setup()`; B panel/intake + persistent `TicketActionsView` (`timeout=None`, `ticket:open|claim|close|edit-category`, `add_view()`) + ephemeral 300s + `is_mod_check`.

Chain `S3.1→S3.2→S3.3A→S3.3B→S3.4A→S3.4B`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `bot/services/ticket_service.py` | Modified | Facade + 3 sub-services |
| `bot/cogs/tickets.py` | Modified | Flow modules, guild delegation |
| `bot/views/tickets.py` | Modified | Panel/persistent/ephemeral |
| `bot/services/ticket_*_db.py`, `schema_inventory.py` | Modified/New | Guild mixins + probe/catalog |
| `migrations/*.sql` | New | FK/cast migration(s) |
| `Diagramas/*.mmd` | Referenced | Sequence/ER/ecosystem |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Duplicate cache/audit | High | One owner; delegate once |
| DB bypasses guild | High | Migrate callers behind service |
| TEXT→UUID lock | Med | Preflight + `USING` + backup |
| Audit orphan blocks FK | High | Retention before nullable `SET NULL` |
| `sb_secret_` vs JWT | Med | Probe ≠ decode; PyJWT legacy only |
| Persistent view loss | Med | Keep `timeout=None`/IDs; startup test |

## Rollback Plan

Each child PR `git revert`. S3.1 code-only. S3.2 backup + `DOWN` migration; abort pre-DDL on fail. S3.3/S3.4 restore monolith via facade; IDs unchanged.

## Dependencies

Baseline `ebe3c7f` (1864/5, 89%, mypy 0, ruff 0 bot/tests), PG17.6 `vozkcckiybebhcclrasa`. S2 archive deferrals consumed.

## Success Criteria

- [ ] 6 PRs ≤800, `S3.1→S3.2→S3.3A/B→S3.4A/B` clean (Q3).
- [ ] Gates completos (Q5): 1864/5, `mypy bot` 0 + `mypy tests` 0, `ruff` 0 inc. scripts, 0 guild gaps, live FK/RLS(9/7/0)/pub(4)/migration, 4 view IDs.
- [ ] Preflights green, DDL validated, only dupe index dropped.
- [ ] Facade graph clean; public APIs preserved.
