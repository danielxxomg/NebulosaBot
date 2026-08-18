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

- [x] S3.2.1 RED: preflight abort + 8-step order + reject drops — 18 GREEN 1899/5
- [x] S3.2.2 Create migrations/018_ticket_integrity_fks.sql 8 steps+DOWN+LOCK_TIMEOUT+backup reconcile 17↔19 (+005 stub, 19 local)
- [x] S3.2.3 GREEN: staging catalog pg_constraint/column/index asserts 1899/5 mypy0 ruff0

## S3.3A Service Query/Cache — DONE s3d3a-query @5aaf728 (≤400)

Query/cache ONLY behind facade — TicketQueryService single cache owner (get_stale_tickets + _ticket_channel_cache: is_ticket_channel/sync_channel_cache/add_channel/discard_channel). Lifecycle stays on facade for S3.3A2. Branch ticket-physical-split-s3d3a-query base 961123b stacked-to-main. Verify `pytest -k ticket_query` `mypy bot`.

- [x] S3.3A.1 RED: facade delegates once, single cache mutation — tests/test_ticket_query_service_facade.py 8 GREEN (was 8 RED)
- [x] S3.3A.2 Extract bot/services/ticket_query_service.py (63) + facade delegates once + add/discard wiring (create/subticket/reopen/close) — 328+379 ≤400
- [x] S3.3A.3 GREEN: 1907/5 mypy 0 ruff 0 — single cache owner, copy-on-sync, no lifecycle extraction

## S3.3A2 Service Lifecycle — DONE s3d3a2-lifecycle @2522d35 (lifecycle behind facade)

TicketLifecycleService behind TicketService (create/close/claim/unclaim/edit_category/create_subticket/reopen/transfer/notes). Branch ticket-physical-split-s3d3a2-lifecycle base 1cf60ba stacked-to-main. Verify `pytest -k ticket_lifecycle` + `pytest -k ticket_query` delegates once.

- [x] S3.3A2.1 RED: lifecycle delegates once, audit single owner — tests/test_ticket_lifecycle_service_facade.py 12 RED → 12 GREEN
- [x] S3.3A2.2 Extract bot/services/ticket_lifecycle_service.py (487) + facade delegates once + cache via query add/discard — 774+817 gross (pure move ~766 body; net new 50 delegates + 237 tests), GGA pass, mypy 0, ruff 0 — commit 2522d35 (size:exception pure extraction, review is move-verification)
- [x] S3.3A2.3 GREEN: lifecycle invariants single owner, cache via query, 31 callers preserved, 1919/5 mypy 0 ruff 0

## S3.3B Service Repair/Channel — DONE s3d3b-repair @ticket-physical-split-s3d3b-repair (repair/channel behind facade)

TicketRepairService (repair/channel/transcript) single evaluate_repair_eligibility owner behind facade. Branch ticket-physical-split-s3d3b-repair base 4883f18 (ticket-physical-split-s3d3a2-lifecycle) stacked-to-main. Verify `pytest -k repair` `mypy bot` `ruff`.

- [x] S3.3B.1 RED: shared eligibility event/sweep/manual race→no-op unresolved→skip — tests/test_ticket_repair_service_facade.py 11 RED → 11 GREEN
- [x] S3.3B.2 Extract bot/services/ticket_repair_service.py (921) + facade delegates once (repair_ticket_from_evidence/handle_channel_delete/sweep_integrity/repair_ticket_by_ref/repair_ticket_manual + create_ticket_channel/close_ticket_full via lifecycle) — countdown kept on facade for patch logger compat — 1217+949 gross (pure move ~949 body; net new 67 delegates + 229 tests), mypy 0, ruff 0
- [x] S3.3B.3 GREEN: race/idempotency listener transcript fakes 1930/5 mypy 0 ruff 0 — single evaluate_repair_eligibility seam preserved

## S3.4A Cog Admin/Lifecycle/Notes/Integrity — DONE s3d4a-cog @301a5aa (cog 4 flows behind facade, 14 RED→GREEN)

4 flows behind TicketsCog async def setup(bot) hybrid, branch ticket-physical-split-s3d4a-cog base ticket-physical-split-s3d3b-repair stacked-to-main. Verify `uv run pytest -q && uv run mypy bot tests && uv run ruff check bot tests`.

- [x] S3.4A.1 RED: setup() once 568/685/722 guild_id=gid, facade delegates once — tests/test_tickets_cog_facade.py 14 RED → 14 GREEN
- [x] S3.4A.2 Create ticket_admin_flow.py(250)/ticket_lifecycle_flow.py(315)/ticket_notes_flow.py(115)/ticket_integrity_flow.py(105) + TicketsCog thin facade (464) delegates via composition, preserve hybrid names, is_mod, guild scoping
- [x] S3.4A.3 GREEN: cog integration 1944/5 mypy 0 ruff 0 bot/tests, guild gaps empty (all get_ticket_by_channel guild_id=gid via flows), 16+8 decorators preserved, no view changes

## S3.4B Views Panel/Persistent/Ephemeral — DONE s3d4b-views @5084441 (views 3 seams behind facade, final S3 slice)

3 seams behind views/tickets.py facade: panel/intake (TicketIntakeModal+TicketPanelView), persistent TicketActionsView (timeout=None), ephemeral 300s category selectors. Branch ticket-physical-split-s3d4b-views base b9d531d (ticket-physical-split-s3d4a-cog) stacked-to-main. Verify `uv run pytest -q && uv run mypy bot && uv run ruff check bot`.

- [x] S3.4B.1 RED: 4 IDs + 2 timeouts + revalidation + t(guild_id) + field_definitions — tests/test_ticket_views_split_facade.py 12 GREEN (was 5 RED pre-facade)
- [x] S3.4B.2 Create ticket_panel.py(477)/ticket_actions.py(384)/ticket_category_select.py(295) + facade re-exports, preserve 4 custom_ids, timeout None + 300s, is_mod_check revalidation (stale mod/closed re-fetch), field_definitions via _CategorySelect
- [x] S3.4B.3 GREEN: 1956/5 mypy bot 0 ruff bot 0, GGA PASSED, facade keeps bot.bot add_view() imports, no cog changes

## Out of Scope

Beyond facade, RLS policies, economy CDC, dashboard auth, drops. E2E disabled.

## Gates final

pytest1864/5 mypy bot0 mypy tests0 ruff0 GUILD_SCOPE_GAPS empty FK/RLS9/7/0/pub4/migration parity 4 view IDs+timeouts.
