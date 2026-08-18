# Proposal: refactor-ticket-domain S2 — Bounded Seams

## Intent
Bounded seams + first repair slice behind facades — not literal 2,170+1,079+1,011 relocation. Guild contract + live parity prerequisite for S3. Refs: `Diagramas/DiagramaSecuencia.mmd`, `Diagramas/DiagramaEntidad-Relacion.mmd`.

## Scope
### In Scope
- **S2.1 Typed 250–300:** `NebulosaContext` Sentinel/Utility, fix 28 mypy test errors, `is_mod` 23/21 tests. Verify `mypy`/`ruff bot tests`.
- **S2.2 Guild DB 300–400:** guild-aware ticket/category/note/audit entry points, one vertical migration, cross-guild denial tests.
- **S2.3 Live parity 300–400:** read-only verifier (FK/RLS/publication/indexes/migrations) → `SchemaInventory`; opt-in live marker. No DDL.
- **S2.4 Repair 350–400:** extract `handle_channel_delete`/`sweep_integrity`/`repair_ticket_by_ref|from_evidence` behind `TicketService` facade; single `evaluate_repair_eligibility`. Total 1200–1500, each ≤800.

### Out of Scope
Full lifecycle/query/views relocation → S3; RLS policies → S3; FK DDL → S3 (verifier only); economy/invalidation → S3.

## Capabilities
### New Capabilities
- `live-schema-verifier`: read-only Supabase parity binder.

### Modified Capabilities
- `ticket-service`: guild contract + repair seam behind facade
- `permission-model`: typed context, preserve `is_mod` dual paths
- `database-layer`: guild-aware mixins, no S2 DDL

## Approach
Delivery A (lifecycle/query/repair) toward B (domain/app/infra). Preserve `TicketService`, `TicketsCog`, `TicketPanelView`/`TicketActionsView`, IDs `ticket:open|claim|close|edit-category`. Stacked-to-main, `auto-chain`, 800 budget. No DDL S2.1–S2.2.

## Affected Areas
| Area | Impact | Description |
|------|--------|-------------|
| `bot/services/ticket_service.py` | Modified | Facade + repair extraction |
| `bot/cogs/tickets.py`, `bot/views/tickets.py` | Modified | Guild checks via service |
| `bot/services/ticket_*_db.py` | Modified | Guild-aware mixins |
| `bot/utils/checks.py`, `bot/core/context.py` | Modified | Typed context |
| `bot/services/schema_inventory.py` | New | Live verifier |
| `tests/` | Modified | Mypy, denial, repair contracts |

## Risks
| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `is_mod` blast 23/21 | Med | Characterization tests first |
| FK TEXT/UUID `categoryId` mismatch | High | Flag only; no DDL |
| Self-ref `parentId` depth>1 | Med | RESTRICT + app depth=1 |
| Persistent view loss | Med | Keep `timeout=None`/IDs/`add_view` |
| Zero-policy RLS misread | Med | Service-role-only + anon→fail |

## Rollback Plan
Each stacked PR `git revert` independently. S2.1–S2.2 code-only (no DDL). S2.3 read-only. S2.4 restores monolithic repair.

## Dependencies
Baseline `ddec186`: 1814 tests, 88.61%, `mypy bot` 0. Supabase `vozkcckiybebhcclrasa` PG17.6 read-only.

## Success Criteria
- [ ] S2.1–S2.4 each ≤800, stacked, green
- [ ] 1814 tests + `mypy bot` 0 + `ruff bot tests` 0
- [ ] Cross-guild denial + `evaluate_repair_eligibility` pass
- [ ] Live bound: mocked+gated = 9 zero-policy / 6 guild-FKs / 4 CDC / 19 migrations

## Assumptions
Bounded S2.1–S2.4; full move → S3. RLS zero-policy service-role-only (publishable denied, anon→fail, no policies S2). FK documented only (note CASCADE, audit SET NULL, category SET NULL, parent RESTRICT+depth=1 — TEXT/UUID mismatch noted). Live credential-gated mocked default. Acceptance = slices + suite + `mypy bot` 0 + live bound.
