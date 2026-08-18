# Tasks: ticket-physical-split S3

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated | ~3600 (6 PRs ≤800) |
| 800-line risk | Low |
| 400-line risk | Low |
| Chained PRs | Yes |
| Delivery | auto-chain |
| Chain | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Low

### Work Units

| # | Goal | PR | Test | Runtime | Rollback |
|---|------|----|------|---------|----------|
|1|Guardrails|S3.1|`pytest -k is_mod`| `LIVE_SUPABASE=1 pytest -m live`| `checks.py` `tickets.py:568/685/722`|
|2|Parity/DDL|S3.2|`pytest -k preflight`| `schema_inventory --check`| `018*.sql`+DOWN|
|3|Query/lifecycle|S3.3A|`pytest -k ticket_service`| N/A| `ticket_*_service.py`|
|4|Repair/channel|S3.3B|`pytest -k repair`| N/A| `ticket_repair_service.py`|
|5|Cog 4 flows|S3.4A|`pytest -k cog`| `pytest -k setup_hook`| `tickets.py`+flows|
|6|Views|S3.4B|`pytest -k view`| `pytest -k persistent_view`| `views/tickets.py`+3|

Chain S3.1→S3.4B → master ebe3c7f.

## S3.1 Guardrails 450–700

Scope 25 is_mod(17+8), 568/685/722+14 db, sb_secret probe guild/ticket+DB/RPC, 11 scripts Ruff. Gates pytest1864/5 mypy0 ruff0 GUILD_SCOPE_GAPS empty. Branch ticket-physical-split-s3d1 base ebe3c7f master. Verify `uv run pytest -q && uv run mypy bot tests && uv run ruff check bot tests scripts`.

- [x] S3.1.1 RED: 25 decorators, guild denial, sb_secret fail-closed, Ruff 11 (EM102×4 TRY003×4 T201×2 SIM102×1)
- [x] S3.1.2 Fix verifier+scripts: sb_secret SELECT probe, PyJWT/JWKS allowlist, DB/RPC catalog, guild_id on 568/685/722+14
- [x] S3.1.3 GREEN: gates pass (1881/5, mypy 0, ruff 0 bot/tests/scripts), live skip closed, no DDL — commit 047fbb6

## S3.2 Parity/DDL 550–800

DDL 1 preflight(dup/UUID/depth/orphans/audit1/1) →2 TEXT→UUID USING cast →3 indexes →4 parentId RESTRICT+depth1 →5 categoryId SET NULL →6 note CASCADE →7 audit SET NULL →8 validate drop idx_ticket_guild_number only (keep idx_ticket_channel). Gates RLS9/7/0 pub4 17vs19 repaired. Branch sdd/s3.2-parity-ddl base sdd/s3.1-guardrails. Verify `pytest -k preflight` `mypy` `ruff`.

- [ ] S3.2.1 RED: preflight abort + 8-step order + reject drops
- [ ] S3.2.2 Create migrations/018_ticket_integrity_fks.sql 8 steps+DOWN+LOCK_TIMEOUT+backup reconcile 17↔19
- [ ] S3.2.3 GREEN: staging catalog pg_constraint/column/index asserts 1864/5

## S3.3A Service Query/Lifecycle

TicketQueryService+TicketLifecycleService behind TicketService single cache/audit owner 31 callers. Branch sdd/s3.3a-service-query-lifecycle base sdd/s3.2-parity-ddl. Verify `pytest -k ticket_service` `mypy bot`.

- [ ] S3.3A.1 RED: facade delegates once, single cache mutation
- [ ] S3.3A.2 Extract ticket_query_service.py+ticket_lifecycle_service.py preserve callers
- [ ] S3.3A.3 GREEN: cache invalidation transfer/reopen mypy0

## S3.3B Service Repair/Channel

TicketRepairService+channel/transcript one evaluate_repair_eligibility. Branch sdd/s3.3b-service-repair-channel base sdd/s3.3a-service-query-lifecycle. Verify `pytest -k repair` `mypy`.

- [ ] S3.3B.1 RED: shared eligibility event/sweep/manual race→no-op unresolved→skip
- [ ] S3.3B.2 Extract ticket_repair_service.py+helpers wire on_channel_delete/sweep_integrity/repair_ticket_*
- [ ] S3.3B.3 GREEN: race/idempotency listener transcript fakes

## S3.4A Cog Admin/Lifecycle/Notes/Integrity

4 flows behind TicketsCog async def setup(bot) hybrid. Branch sdd/s3.4a-cog-flows base sdd/s3.3b-service-repair-channel. Verify `pytest -k cog` `mypy` `ruff`.

- [ ] S3.4A.1 RED: setup() once 568/685/722 cross-guild denial
- [ ] S3.4A.2 Create ticket_admin_flow.py/ticket_lifecycle_flow.py/ticket_notes_flow.py/ticket_integrity_flow.py wrappers
- [ ] S3.4A.3 GREEN: cog integration 25 decorators GUILD_SCOPE_GAPS empty

## S3.4B Views Panel/Persistent/Ephemeral

3 seams via views/tickets.py 4 IDs ticket:open|claim|close|edit-category timeout=None+add_view() 300s+is_mod_check. Branch sdd/s3.4b-views base sdd/s3.4a-cog-flows. Verify `pytest -k view` full suite.

- [ ] S3.4B.1 RED: IDs/timeouts immutable stale mod/closed rejected t(guild_id)+deploy_ticket_panel(None) localized
- [ ] S3.4B.2 Create ticket_panel.py/ticket_actions.py/ticket_category_select.py pass field_definitions to TicketIntakeModal
- [ ] S3.4B.3 GREEN: panel/intake persistent startup ephemeral revalidation 1864/5

## Out of Scope

Beyond facade, RLS policies, economy CDC, dashboard auth, drops. E2E disabled.

## Gates final

pytest1864/5 mypy bot0 mypy tests0 ruff0 GUILD_SCOPE_GAPS empty FK/RLS9/7/0/pub4/migration parity 4 view IDs+timeouts.
