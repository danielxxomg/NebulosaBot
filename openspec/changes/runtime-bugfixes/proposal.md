# Proposal: Runtime Bugfixes

## Intent

Fix 4 critical runtime bugs (FK violations, watchdog spam, CDC event drops, silent reconnect) plus move `banana.png` to correct path. Blocks live bot.

## Scope

### In Scope
- **C1**: Migration to drop the 4 FK constraints to `user` table AND drop the vestigial `user` table itself (verified: dashboard specs do not reference `user`; bot never writes to it)
- **C2**: Fix `_event_count` to track received (not processed) events
- **C3**: Fix `_extract_guild_id` for `table=None` payloads using supabase-py 2.31.0 realtime docs (Context7) — no debug logging, fix per documented payload structure
- **C4**: Add reconnection resilience logging
- **S1**: Rename root `banana.png` (actually WebP) → `assets/images/banana.webp`, update `bot/cogs/ocio.py` path reference, delete the 422-byte PNG placeholder in `assets/images/`

### Out of Scope
- Tooling upgrades (ruff, mypy, pre-commit, CI) → `tooling-rigor`
- i18n, setup wizard, large cog refactors

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `initial-schema`: New migration drops 4 FK constraints (`member.userId`, `infraction.targetId`, `infraction.moderatorId`, `ticket.authorId`) and drops the vestigial `user` table. Spec updated to remove `user` table and FK references.
- `cache-sync-realtime`: Fix watchdog counter (C2), `table=None` handling via supabase-py docs (C3), reconnect logging (C4).
- `ocio-commands`: Asset path updated from `banana.png` to `banana.webp`.

## Approach

**C1**: Migration `006_drop_user_table.sql` — `ALTER TABLE ... DROP CONSTRAINT` for all 4 FKs to `"user"(id)`, then `DROP TABLE IF EXISTS "user"`. Update `openspec/specs/initial-schema/spec.md` to remove `user` table and FK references.

**C2**: Add `_received_count`, increment at top of `_handle_cdc`. Watchdog checks it.

**C3**: Consult supabase-py 2.31.0 realtime docs via Context7 for the actual CDC payload structure. Fix `_extract_guild_id` to handle the real structure (no debug logging, no defensive fallback — fix per docs).

**C4**: Log WebSocket close/reconnect. Escalation after N unhealthy cycles.

**S1**: `git mv banana.png assets/images/banana.webp`, update `bot/cogs/ocio.py:25` path to `Path("assets/images/banana.webp")`, delete `assets/images/banana.png` (422-byte placeholder).

## Affected Areas

| Area | Impact |
|------|--------|
| `migrations/006_drop_user_table.sql` | New |
| `openspec/specs/initial-schema/spec.md` | Modified (remove `user` table + FK refs) |
| `bot/core/realtime.py` | Modified (C2, C3, C4) |
| `bot/cogs/ocio.py` | Modified (path `banana.png` → `banana.webp`) |
| `banana.png` → `assets/images/banana.webp` | Moved/renamed |
| `assets/images/banana.png` | Deleted (422-byte placeholder) |
| `tests/core/test_realtime.py` | Modified |
| `tests/cogs/test_ocio.py` | Modified (if exists) |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Dashboard uses `user` table | Low | Verified: dashboard specs (`dashboard-fixes`, `dashboard-ticket-view`) do not reference `user`. Bot never writes to it. |
| C3 fix based on docs differs from real payload | Medium | Context7 provides supabase-py 2.31.0 authoritative docs; verify payload field names match before finalizing spec |
| WebP file not accepted by Discord | Low | discord.py 2.7.1 supports WebP attachments via `discord.File` |

## Rollback Plan

- **C1**: Reverse migration re-adds `user` table + 4 FKs (requires data backfill if any `user` rows existed, but table was never populated)
- **C2–C4**: Revert `realtime.py`
- **S1**: Revert `ocio.py` path + `git mv assets/images/banana.webp banana.png`

## Dependencies

- Supabase access to apply migration

## Success Criteria

- [ ] `member` upsert succeeds without FK violation
- [ ] `user` table no longer exists; no FK references remain
- [ ] Watchdog silent when events arrive but are skipped
- [ ] No `CDC event for None` warnings
- [ ] WebSocket close/reconnect logged
- [ ] `/banana` command works (sends WebP image)
- [ ] `uv run pytest` passes

## Proposal Question Round

1. **Drop `user` table or just FKs?** `infraction` and `ticket` also reference `user`. Should we drop the table entirely or just FKs? **Assumption**: Drop FKs only.

2. **C3 payload debugging**: Capture raw payload or fix defensively? **Assumption**: Defensive handling + debug log.

3. **banana.png conflict**: Root file (12888B, today) vs `assets/images/` (422B, Jul 4). Which is real? **Assumption**: Root file is real.
