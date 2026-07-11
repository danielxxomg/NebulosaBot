# Apply Progress: Edit Category — Channel Audit Feedback

**Change**: `edit-category-audit-feedback`
**Mode**: Strict TDD / OpenSpec
**Test runner**: `uv run pytest`

## Task Completion Status

### Phase 1: i18n Foundation

- [x] 1.1 RED: Add `test_edit_category_audit_keys_es`/`_en` — assert `t(guild, "tickets.actions.edit_category_audit_title")` and `..._audit_description` return non-empty; add placeholders to es_data+en_data fixtures
- [x] 1.2 RED: Add `test_edit_category_audit_placeholders_resolve` — assert `t(..., ..._audit_description, old_category="Support", new_category="Billing", actor="<@123>")` contains all three with no `{...}` left
- [x] 1.3 GREEN: Add `edit_category_audit_title` + `edit_category_audit_description` under `tickets.actions` in `bot/locales/en.json` with placeholders
- [x] 1.4 GREEN: Add mirrored keys under `tickets.actions` in `bot/locales/es.json` with placeholders
- [x] 1.5 REFACTOR: Verify both JSON parse and keys sit alongside sibling `edit_category_*` keys

### Phase 2: View Audit Embed

- [x] 2.1 RED: Add `test_select_success_sends_channel_audit_embed` — mock `channel.send`; assert one non-ephemeral `info_embed` with old label (Support), new label (Billing), actor mention
- [x] 2.2 RED: Add `test_select_audit_uses_dash_when_categoryid_none` — `categoryId=None`; assert audit contains `—`, never raw UUID
- [x] 2.3 RED: Add `test_select_audit_send_failure_is_non_fatal` — `channel.send` raises `discord.HTTPException`; assert callback completes, ephemeral success sent, `channel.send` was attempted
- [x] 2.4 GREEN: In `bot/views/tickets.py`, add `info_embed` to import line
- [x] 2.5 GREEN: After ephemeral success: `old_category_id = ticket_row.get("categoryId")`; `old_label = next(...)`; `old_category_name = old_label if old_label is not None else "—"`
- [x] 2.6 GREEN: Build `audit_embed = info_embed(t(..., "tickets.actions.edit_category_audit_title"), t(..., "tickets.actions.edit_category_audit_description", old_category=..., new_category=..., actor=...), ...)`
- [x] 2.7 GREEN: `await channel.send(embed=audit_embed)` in `try: except discord.HTTPException: logger.warning(...)`; no re-raise
- [x] 2.8 REFACTOR: Ensure `_make_select_interaction` sets `user.mention = f"<@{user_id}>"`

### Phase 3: Verification

- [x] 3.1 Run focused tests — all new and existing tests pass (111 tests)
- [x] 3.2 Run full coverage — 87.97% (threshold: 75%) — satisfied
- [x] 3.3 Run ruff check — no lint errors
- [x] 3.4 Run py_compile — build check passes

### Phase 4: Cleanup

- [x] 4.1 Verify no raw UUID leak path in audit embed
- [x] 4.2 Confirm rollback path documented

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.1 | `tests/test_tickets_i18n.py` | Unit | ✅ 105/105 | ✅ Written (`test_edit_category_audit_keys_es`/`_en`) | ✅ Passed | ➖ Single scenario (key existence) | ✅ Clean |
| 1.2 | `tests/test_tickets_i18n.py` | Unit | ✅ 105/105 | ✅ Written (`test_edit_category_audit_placeholders_resolve`) | ✅ Passed | ✅ 2 cases (fixture keys + production JSON) | ✅ Clean |
| 1.3 | `bot/locales/en.json` | Resource | N/A (JSON) | N/A (resource file) | ✅ JSON parses, keys present | ✅ Verified by 1.1 + 1.2 tests | ✅ Keys alongside sibling `edit_category_*` |
| 1.4 | `bot/locales/es.json` | Resource | N/A (JSON) | N/A (resource file) | ✅ JSON parses, keys present | ✅ Verified by 1.1 + 1.2 tests | ✅ Keys alongside sibling `edit_category_*` |
| 1.5 | Both locale files | Resource | N/A (refactor) | N/A | N/A | N/A | ✅ Keys sit alongside siblings |
| 2.1 | `tests/test_ticket_views.py` | Unit | ✅ 105/105 | ✅ Written (`test_select_success_sends_channel_audit_embed`) | ✅ Passed | ✅ 3 cases: old label (Support), new label (Billing), actor mention | ✅ Clean |
| 2.2 | `tests/test_ticket_views.py` | Unit | ✅ 105/105 | ✅ Written (`test_select_audit_uses_dash_when_categoryid_none`) | ✅ Passed | ✅ 2 cases: dash fallback + no UUID leak | ✅ Clean |
| 2.3 | `tests/test_ticket_views.py` | Unit | ✅ 105/105 | ✅ Written (`test_select_audit_send_failure_is_non_fatal`) | ✅ Passed | ✅ 2 cases: ephemeral success + channel.send attempted | ✅ Clean |
| 2.4 | `bot/views/tickets.py` | Prod | N/A (import) | N/A | ✅ Import added | N/A | ✅ Single import line |
| 2.5 | `bot/views/tickets.py` | Prod | N/A (new code) | N/A (covered by 2.1/2.2) | ✅ Passed (tests 2.1+2.2 green) | ✅ Resolved label + dash fallback | ✅ Clean |
| 2.6 | `bot/views/tickets.py` | Prod | N/A (new code) | N/A (covered by 2.1) | ✅ Passed (test 2.1 green) | ✅ All 3 placeholders verified | ✅ Clean |
| 2.7 | `bot/views/tickets.py` | Prod | N/A (new code) | N/A (covered by 2.3) | ✅ Passed (test 2.3 green) | ✅ HTTPException caught, non-fatal | ✅ Clean |
| 2.8 | `tests/test_ticket_views.py` | Test | ✅ 105/105 | N/A (refactor) | N/A | N/A | ✅ `_make_select_interaction` sets `user.mention` |
| 3.1 | Both test files | Verify | N/A | N/A | ✅ 111/111 passed | N/A | N/A |
| 3.2 | Full suite | Verify | N/A | N/A | ✅ 87.97% / 75% | N/A | N/A |
| 3.3 | Linter | Verify | N/A | N/A | ✅ 0 errors | N/A | N/A |
| 3.4 | Build | Verify | N/A | N/A | ✅ py_compile pass | N/A | N/A |
| 4.1 | Code review | Verify | N/A | N/A | ✅ No UUID in audit text | N/A | N/A |
| 4.2 | Code review | Verify | N/A | N/A | ✅ Rollback: revert callback lines + remove 4 i18n keys | N/A | N/A |

### Remediation Evidence (post-verify fixes)

| Fix | File | What Changed | TDD Evidence |
|-----|------|--------------|--------------|
| CRITICAL-1 | `tests/test_ticket_views.py` | `test_select_success_sends_channel_audit_embed`: added both categories to options, assert old label "Support" | RED: test asserted "—" (weak). GREEN: now asserts "Support" (old label resolved) + "Billing" (new label) |
| CRITICAL-2 | `tests/test_tickets_i18n.py` | Added `TestProductionLocaleAuditKeys` with 6 tests loading real JSON files | RED: tests load `bot/locales/{en,es}.json` directly. GREEN: 6/6 pass — keys and placeholders confirmed |
| CRITICAL-3 | `openspec/changes/.../apply-progress.md` | Created this artifact with full TDD Cycle Evidence | N/A (meta-artifact) |
| WARNING-1 | `tests/test_ticket_views.py` | `_make_select_interaction` now sets `user.mention = f"<@{user_id}>"` | RED: N/A (refactor). GREEN: 111/111 tests pass |
| WARNING-2 | `tests/test_ticket_views.py` | `test_select_audit_send_failure_is_non_fatal`: added `channel.send.assert_awaited_once()` | RED: test lacked send assertion. GREEN: assertion now confirms send was attempted |

## Test Summary

- **Total tests written for change**: 12 (6 original + 6 production locale)
- **Total tests passing**: 111/111 (focused suite)
- **Layers used**: Unit (12), Resource verification (6)
- **Pure functions created**: 0 (view callback + JSON resource checks)
