# Tasks: Edit Category — Channel Audit Feedback

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 140–180 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | i18n keys + view audit embed + TDD tests | PR 1 | base: main; single PR well under 400 lines |

## Phase 1: i18n Foundation (RED first)

- [x] 1.1 RED: Add `test_edit_category_audit_keys_es`/`_en` to `tests/test_tickets_i18n.py` — assert `t(guild, "tickets.actions.edit_category_audit_title")` and `..._audit_description` return non-empty; add placeholders to es_data+en_data fixtures with `{old_category}`, `{new_category}`, `{actor}`
- [x] 1.2 RED: Add `test_edit_category_audit_placeholders_resolve` — assert `t(..., ..._audit_description, old_category="Support", new_category="Billing", actor="<@123>")` contains all three with no `{...}` left
- [x] 1.3 GREEN: Add `edit_category_audit_title` + `edit_category_audit_description` under `tickets.actions` in `bot/locales/en.json` with placeholders
- [x] 1.4 GREEN: Add mirrored keys under `tickets.actions` in `bot/locales/es.json` (neutral/professional Spanish) with placeholders
- [x] 1.5 REFACTOR: Verify both JSON parse and keys sit alongside sibling `edit_category_*` keys

## Phase 2: View Audit Embed (RED first)

- [x] 2.1 RED: Add `test_select_success_sends_channel_audit_embed` to `TestEditCategorySelect` — mock `channel.send`; assert one non-ephemeral `info_embed` via `channel.send` with old label, new label, actor mention; ephemeral success still sent
- [x] 2.2 RED: Add `test_select_audit_uses_dash_when_categoryid_none` — `categoryId=None`; assert audit contains `—`, never raw UUID
- [x] 2.3 RED: Add `test_select_audit_send_failure_is_non_fatal` — `channel.send` raises `discord.HTTPException`; assert callback completes, no second user error, ephemeral success sent
- [x] 2.4 GREEN: In `bot/views/tickets.py`, add `info_embed` to `from bot.utils.embeds import` line (line 20)
- [x] 2.5 GREEN: After ephemeral success (line 925) in `_EditCategorySelect.callback`: `old_category_id = ticket_row.get("categoryId")`; `old_label = next((opt.label for opt in self.options if opt.value == old_category_id), None)`; `old_category_name = old_label if old_label is not None else "—"`
- [x] 2.6 GREEN: Build `audit_embed = info_embed(t(guild_id, "tickets.actions.edit_category_audit_title"), t(guild_id, "tickets.actions.edit_category_audit_description", old_category=old_category_name, new_category=category_name, actor=interaction.user.mention), guild_id=guild_id, bot=bot, guild=guild)`
- [x] 2.7 GREEN: `await channel.send(embed=audit_embed)` in `try: except discord.HTTPException: logger.warning(...)`; no re-raise, no user-facing error
- [x] 2.8 REFACTOR: Ensure `_make_select_interaction` sets `user.mention = "<@{user_id}>"` if missing

## Phase 3: Verification

- [x] 3.1 Run `uv run pytest tests/test_ticket_views.py tests/test_tickets_i18n.py -v` — all new and existing tests pass
- [x] 3.2 Run `uv run pytest --cov=bot --cov-report=term` — confirm coverage threshold (≥0.70) still satisfied
- [x] 3.3 Run `uv run ruff check bot/views/tickets.py bot/locales/ tests/test_ticket_views.py tests/test_tickets_i18n.py` — no lint errors
- [x] 3.4 Run `python -m py_compile bot/__main__.py` — build check passes

## Phase 4: Cleanup

- [x] 4.1 Verify no raw UUID leak path in audit embed (old_category_id never reaches channel.send text)
- [x] 4.2 Confirm rollback path documented: revert callback lines + remove 4 i18n keys
