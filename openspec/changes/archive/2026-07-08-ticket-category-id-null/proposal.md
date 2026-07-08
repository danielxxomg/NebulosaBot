# Proposal: Fix ticket_category_id NULL Blocking Ticket Creation

## Intent

New guilds cannot create tickets because `ticket_category_id` defaults to `None` and no bot command exists to set it. Three flows are broken: ticket creation (button), sub-ticket creation (`/sub_ticket`), and ticket reopen. Admins must discover the web dashboard independently — no in-bot guidance exists.

## Scope

### In Scope
- Add `/setup` wizard command (hybrid, `@is_admin()`) that configures `ticket_category_id`, `mod_role_id`, `log_channel_id`, and `language` in one guided flow
- Improve "Not Configured" error messages in all 3 blocked flows to include actionable hints (`/setup` command name + dashboard URL)
- Fix dashboard hint text: change misleading "UUID" label to "Discord Category Channel ID (right-click → Copy Channel ID)"

### Out of Scope
- Auto-creating category channels on guild join or on demand (deferred — requires `Manage Channels` permission + admin consent)
- `/setup` wizard for ALL config fields (only critical blockers: ticket_category_id, mod_role_id, log_channel_id, language)
- DB schema changes (none needed)

## Capabilities

### New Capabilities
- `setup-wizard`: `/setup` hybrid command gated by `@is_admin()` — accepts `ticket_category` (CategoryChannel), optional `mod_role`, `log_channel`, `language`. Validates Discord IDs exist before saving. Uses `t()` for i18n.

### Modified Capabilities
- `ticket-commands`: Error message wording in "Not Configured" blocks (`bot/cogs/tickets.py:377-384`, `:1172-1178`) and `reopen_ticket` ValueError (`bot/services/ticket_service.py:460-464`) — must now suggest `/setup` or dashboard URL instead of generic message.

## Approach

Per exploration recommendation (Option D — Hybrid):

1. **Add `/setup` command** in `TicketsCog` or new `SetupCog`. Use `discord.CategoryChannel` converter for automatic resolution. Save via `guild_service.save_config()`. All strings through `t()`.
2. **Update error messages** in the 3 blocked flows to say: "Run `/setup` or configure via the dashboard: `<dashboard_url>`"
3. **Fix dashboard hint** in `dashboard/app/(authenticated)/guilds/[guildId]/config/page.tsx:78-83` — change label from "UUID" to "Discord Category Channel ID"
4. **Add i18n keys** to `en.json` and `es.json` for new command and error strings

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `bot/cogs/tickets.py:377-384` | Modified | "Open Ticket" error message |
| `bot/cogs/tickets.py:1172-1178` | Modified | `/sub_ticket` error message |
| `bot/services/ticket_service.py:460-464` | Modified | `reopen_ticket` ValueError message |
| `bot/cogs/` (new or existing cog) | New | `/setup` command implementation |
| `bot/locales/en.json` | Modified | New i18n keys |
| `bot/locales/es.json` | Modified | New i18n keys |
| `dashboard/.../config/page.tsx:78-83` | Modified | Fix hint text |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Admin doesn't know Discord Channel ID for `/setup` | Medium | Accept CategoryChannel converter (Discord auto-resolves); also point to dashboard |
| i18n keys missing in one locale | Low | `t()` falls back to raw key; test both locales |
| Dashboard/bot config desync | Low | Supabase is source of truth; webhook invalidates cache |

## Rollback Plan

Revert the 3 modified files (`tickets.py`, `ticket_service.py`, `page.tsx`) and delete the new `/setup` command code. No DB migrations — purely code changes. Dashboard hint revert is a single label string.

## Dependencies

- None (no new libraries, no DB changes)

## Success Criteria

- [ ] `/setup` command accepts `ticket_category` and saves to guild config
- [ ] "Open Ticket" button shows actionable error when `ticket_category_id` is None
- [ ] `/sub_ticket` shows actionable error when `ticket_category_id` is None
- [ ] `reopen_ticket` error message references `/setup` or dashboard
- [ ] Dashboard config page shows "Discord Category Channel ID" not "UUID"
- [ ] All new strings use `t()` and exist in both `en.json` and `es.json`

## Estimated Changed Lines

~200-300 lines (new `/setup` command: ~120 lines, error message updates: ~30 lines, i18n keys: ~40 lines, dashboard hint: ~5 lines, tests: ~80 lines). Within 800-line review budget.

## Proposal Question Round

These questions would improve the proposal by uncovering edge cases and product decisions:

1. **Permission escalation**: Should `/setup` also accept a `log_channel` parameter, or should that remain dashboard-only? (Affects scope of the wizard.)
2. **Existing guilds**: For guilds that already have `ticket_category_id = None`, should the error message also mention they need to create a TicketCategory via `/create_category` first, or is that a separate onboarding concern?
3. **Dashboard URL**: Is there a stable dashboard URL to include in error messages, or should we use a placeholder/configurable value?
4. **Partial setup**: If an admin runs `/setup` but only provides `ticket_category` (skipping mod_role, log_channel), should we save partial config or require all fields?
