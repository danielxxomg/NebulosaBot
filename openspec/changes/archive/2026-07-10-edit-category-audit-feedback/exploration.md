## Exploration: Edit Category — Channel Audit Feedback

### Current State

When a staff member uses **Edit Category** on a ticket, the flow is:

1. **View** (`bot/views/tickets.py`, `_EditCategorySelect.callback`, lines 820–925):
   - Re-validates mod/admin, re-fetches ticket from DB, calls `ticket_service.edit_ticket_category()`.
   - On success: sends an **ephemeral** `success_embed` to the actor only, showing the new category name.
   - No message is sent to the ticket channel itself.

2. **Service** (`bot/services/ticket_service.py`, `edit_ticket_category`, lines 334–449):
   - Fetches `pre` ticket row (holds old `categoryId`).
   - Validates mod/admin, checks per-user-per-category limit.
   - Updates `categoryId` in DB via `update_ticket()`.
   - Writes an **audit row** to the database (`insert_audit_row` with action `edit_category`).
   - Renames the Discord channel (best effort).
   - Returns `(Ticket, rename_succeeded: bool)`.
   - Does NOT send any channel message.

3. **i18n** (`bot/locales/en.json`, `es.json` under `tickets.actions.edit_category_*`):
   - `edit_category_success` / `edit_category_success_description` — ephemeral-only copy, references `{category}` (new name only).
   - No keys exist for a channel-visible audit message with before/after.

4. **Tests** (`tests/test_ticket_views.py`, `tests/test_ticket_service.py`):
   - View tests cover: mod-only gate, closed rejection, limit error mapping, success ephemeral message.
   - Service tests cover: DB update, channel rename, audit row, denial, closed, limit, not-found.
   - No tests for channel-visible audit messages (none exist yet).

### Affected Areas

- `bot/views/tickets.py` — `_EditCategorySelect.callback` (lines 820–925): add `channel.send()` after success.
- `bot/locales/en.json` — add new i18n keys for channel audit embed (before/after copy).
- `bot/locales/es.json` — mirror Spanish translations for the new keys.
- `tests/test_ticket_views.py` — add tests verifying the channel audit embed is sent on success.
- `tests/test_tickets_i18n.py` — verify new i18n keys exist in both locales.

### Key Finding: Old Category Name Availability

**Yes, the old category name is available at success time.** The view callback re-fetches `ticket_row` from DB at line 846 (before the service call). This row contains the OLD `categoryId`. The view also holds `self.options` (list of `discord.SelectOption` with all category labels). The old name can be resolved with:

```python
old_category_id = ticket_row.get("categoryId")
old_category_name = next(
    (opt.label for opt in self.options if opt.value == old_category_id),
    old_category_id or "—",
)
```

This mirrors the existing pattern at line 873–876 used to resolve the new category name.

### Approaches

1. **View-owned channel embed** — Send a non-ephemeral `info_embed` to the ticket channel from the view callback after the service succeeds.
   - Pros: Minimal change surface (view layer only), follows existing claim/open patterns where the view sends channel messages, no service signature changes, view already has all needed data (old `categoryId` from `ticket_row`, `self.options` for label resolution).
   - Cons: Audit visibility lives in the view rather than the service — if another caller invokes `edit_ticket_category` directly, it won't produce the channel message.
   - Effort: **Low** — ~15 lines in view + 4 i18n keys + 2–3 tests.

2. **Service-owned channel message** — Have `edit_ticket_category` send the embed to the channel directly, accepting a `channel` param (already passed).
   - Pros: All callers get the audit message automatically. Business logic owns the full side-effect chain.
   - Cons: Service currently does NOT send Discord messages (only DB + rename). Adding `channel.send()` with i18n embed construction breaks the current service boundary (services don't import `t()` or embed factories). Increases service complexity and test surface.
   - Effort: **Medium** — service changes + i18n import + embed import + new test fixtures for `channel.send` mock.

3. **Hybrid: service returns old category ID, view sends embed** — Modify the service return to include `old_category_id`, letting the view resolve both names.
   - Pros: Clean data flow, service stays pure (no Discord message sending).
   - Cons: Changes the service return type (breaking change to callers/tests). Over-engineering — the view already has the old `categoryId` from `ticket_row` before the service call.
   - Effort: **Medium** — service signature change + view update + test updates for all callers.

### Recommendation

**Approach 1: View-owned channel embed.** Rationale:

- The view already has all the data it needs (`ticket_row["categoryId"]` for old, `self.options` for label resolution). No service changes required.
- Follows the established pattern: ticket creation (`channel.send` at line 213), claim (`interaction.response.edit_message` at line 556) — the view layer owns channel-visible Discord messages.
- The only caller of `edit_ticket_category` is this view callback — no risk of missing audit messages from other call sites.
- Smallest correct change: 4 new i18n keys, ~15 lines in the view, 2–3 new tests.

Implementation sketch for the view callback (after the existing ephemeral success at line 918–925):

```python
# Channel audit embed — visible to all ticket participants.
old_category_id = ticket_row.get("categoryId")
old_category_name = next(
    (opt.label for opt in self.options if opt.value == old_category_id),
    old_category_id or "—",
)
try:
    await channel.send(
        embed=info_embed(
            t(guild_id, "tickets.actions.edit_category_audit_title"),
            t(
                guild_id,
                "tickets.actions.edit_category_audit_description",
                old_category=old_category_name,
                new_category=category_name,
                actor=interaction.user.mention,
            ),
            guild_id=guild_id, bot=bot, guild=guild,
        )
    )
except discord.HTTPException:
    logger.warning(
        "Failed to send edit_category audit embed in channel %s",
        channel.id,
    )
```

### Risks

- **Low**: If `old_category_id` is `None` (ticket created before categories existed), the fallback `"—"` is acceptable. The i18n key should handle this gracefully.
- **Low**: `channel.send()` can fail (permissions, channel deleted). The `try/except` with logging matches the existing rename-failure pattern (line 434–440).
- **None**: No breaking changes to service signatures or existing tests.

### Ready for Proposal

**Yes.** The orchestrator can proceed to `sdd-propose`. The change is well-scoped:
- 4 new i18n keys (en + es)
- ~15 lines added to the view callback
- 2–3 new test cases (channel embed sent on success, old name fallback when `categoryId` is `None`, `channel.send` failure is non-fatal)
- No service, model, or DB changes needed
