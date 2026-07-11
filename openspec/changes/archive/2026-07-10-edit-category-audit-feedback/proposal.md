# Proposal: Edit Category — Channel Audit Feedback

## Intent

Staff edit a ticket's category with no visible trace in the ticket channel — only the actor sees an ephemeral success. Staff want a channel-visible audit message showing old → new category so participants can see who changed what.

## Scope

### In Scope
- Non-ephemeral `info_embed` to the ticket channel after `edit_ticket_category` succeeds, showing old → new category + actor mention.
- Resolve old category name from pre-update `ticket_row["categoryId"]` + `self.options`; fallback `"—"` when `None`.
- New i18n keys (`edit_category_audit_title`, `edit_category_audit_description`) in both locales with `{old_category}`, `{new_category}`, `{actor}` placeholders.
- Non-fatal `channel.send` failure (log warning, don't break the edit).

### Out of Scope
- Service-layer changes (signature, DB, audit row unchanged).
- Retroactive audit for past edits.
- Dashboard-side category edit feedback.

## Capabilities

### New Capabilities
<!-- None — all behavior extends existing specs. -->

### Modified Capabilities
- `ticket-views`: Edit Category success MUST send a channel-visible `info_embed` (old → new category + actor), in addition to the existing ephemeral success.
- `i18n-system`: New `tickets.actions.edit_category_audit_*` keys with `{old_category}`, `{new_category}`, `{actor}` placeholders in both locales.

## Approach

**View-owned channel embed** (exploration Approach 1). `_EditCategorySelect.callback` already holds `ticket_row` (pre-update, old `categoryId`) and `self.options` (all labels). After the existing ephemeral success, resolve old name via `self.options`, build an `info_embed` with new i18n keys, and `await channel.send(embed=...)`. Wrap in `try/except discord.HTTPException` matching the rename-failure pattern. No service changes.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `bot/views/tickets.py` | Modified | `_EditCategorySelect.callback` (~10 lines after ephemeral success) |
| `bot/locales/en.json` | Modified | 2 new keys under `tickets.actions` |
| `bot/locales/es.json` | Modified | 2 mirrored Spanish keys |
| `tests/test_ticket_views.py` | Modified | Audit embed sent on success; old name fallback; send failure non-fatal |
| `tests/test_tickets_i18n.py` | Modified | New keys present in both locales |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `channel.send` fails (permissions, deleted channel) | Low | `try/except discord.HTTPException` + `logger.warning`; edit succeeds |
| Old `categoryId` is `None` (pre-category tickets) | Low | Fallback `"—"` in label resolution |
| Audit message seen by non-staff participants | Low | Intended — transparency for ticket participants |

## Rollback Plan

Revert the ~10 callback lines and remove the 4 i18n keys. No DB migration, no service changes, no structural changes.

## Dependencies

- None — old `categoryId`, `self.options`, `channel`, and `interaction.user` are already available in the callback.

## Success Criteria

- [ ] Edit Category sends a non-ephemeral `info_embed` to the ticket channel showing old → new category + actor mention
- [ ] Ephemeral success to actor still works (unchanged)
- [ ] `channel.send` failure does not break the edit
- [ ] New i18n keys exist in both `en.json` and `es.json`
- [ ] `uv run pytest tests/test_ticket_views.py tests/test_tickets_i18n.py` passes
