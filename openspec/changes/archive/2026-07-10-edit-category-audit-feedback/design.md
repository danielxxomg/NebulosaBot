# Design: Edit Category — Channel Audit Feedback

## Technical Approach

Extend `_EditCategorySelect.callback` after its successful service call and existing ephemeral confirmation. The callback already re-fetches the pre-update ticket row and owns the active select options, so it can resolve both category labels without changing `TicketService`. It will send a non-ephemeral localized `info_embed` to the ticket channel; this is an independent best-effort notification.

## Architecture Decisions

| Option | Tradeoff | Decision |
|---|---|---|
| Send from the view | Direct service callers would not notify the channel | Chosen: this is the only caller and preserves the cog/view vs. service boundary. |
| Send from `TicketService` | Broader side effect; requires i18n/embed dependencies in business logic | Rejected: violates current service responsibilities and scope. |
| Return old category from service | Changes a stable return contract | Rejected: callback already has the fresh old value. |
| Treat message failure as edit failure | Misrepresents completed DB update | Rejected: catch `discord.HTTPException`, warn, retain success. |

**Rationale:** This follows the existing view-owned Discord-message pattern while leaving cache, Supabase, database audit rows, and service contracts unchanged. Cache-first/CDC behavior is not involved because the callback already performs the required fresh DB lookup.

## Data Flow

```text
Staff selects category
  -> callback re-fetches ticket row (old categoryId)
  -> TicketService edits DB, writes DB audit row, best-effort renames channel
  -> ephemeral success to actor (unchanged)
  -> callback resolves old/new labels from select options
  -> channel.send(info_embed(old -> new, actor))
       \-> HTTPException: warning only; edit remains successful
```

## File Changes

| File | Action | Description |
|---|---|---|
| `bot/views/tickets.py` | Modify | Import `info_embed`; build and best-effort send the localized channel audit embed after success. |
| `bot/locales/en.json` | Modify | Add English audit title and description keys. |
| `bot/locales/es.json` | Modify | Add equivalent Spanish audit keys. |
| `tests/test_ticket_views.py` | Modify | Add callback success, missing-old-category, and send-failure tests. |
| `tests/test_tickets_i18n.py` | Modify | Assert both locale files provide the audit keys and required placeholders. |

## Interfaces / Contracts

New keys under `tickets.actions` in each locale:

```json
"edit_category_audit_title": "...",
"edit_category_audit_description": "... {old_category} ... {new_category} ... {actor} ..."
```

`old_category` is the label matching fresh `ticket_row["categoryId"]`; use `old_category_id or "—"` when it is absent or no longer present in options. `new_category` uses the existing selected-label resolution. `actor` is `interaction.user.mention`. The embed is constructed with `info_embed(..., guild_id=guild_id, bot=bot, guild=guild)` and sent without `ephemeral=True`.

## Failure Handling

The service `ValueError` paths and the actor's ephemeral success behavior remain unchanged. Wrap only `await channel.send(...)` in `except discord.HTTPException`; log a warning including the channel ID with exception context and do not emit a second user-facing error or roll back the edit. Do not catch broader exceptions.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | Successful edit | Mock service/channel; assert one non-ephemeral `info_embed` contains old label, new label, actor mention, while ephemeral success remains. |
| Unit | Old category absent | Fresh row has `categoryId=None`; assert audit description uses `—`. |
| Unit | Notification failure | `channel.send` raises `discord.HTTPException`; assert callback completes and ephemeral success was sent. |
| Unit | Locale contract | Load/read both locale JSON files; assert both keys and `{old_category}`, `{new_category}`, `{actor}` placeholders. |
| Regression | Existing edit outcomes | Run `uv run pytest tests/test_ticket_views.py tests/test_tickets_i18n.py`; implementation is strict TDD (RED tests first). |

## Migration / Rollout

No migration required. Deploy with the normal bot release; rollback is removal of the callback notification and the two keys from each locale.

## Open Questions

None.
