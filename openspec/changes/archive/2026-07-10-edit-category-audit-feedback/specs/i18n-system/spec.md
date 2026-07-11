# Delta for i18n-system

## ADDED Requirements

### Requirement: Edit category audit i18n keys

The system MUST provide `tickets.actions.edit_category_audit_title` and `tickets.actions.edit_category_audit_description` keys in both `en.json` and `es.json`. These keys MUST support `{old_category}`, `{new_category}`, and `{actor}` placeholder tokens.

#### Scenario: Audit keys present in both locales

- GIVEN `en.json` and `es.json` under `bot/locales/`
- WHEN `t(guild_id, "tickets.actions.edit_category_audit_title")` is called for each locale
- THEN a non-empty string is returned from both `en.json` and `es.json`

#### Scenario: Audit placeholders resolve correctly

- GIVEN `tickets.actions.edit_category_audit_description` contains `{old_category}`, `{new_category}`, `{actor}`
- WHEN `t(guild_id, "tickets.actions.edit_category_audit_description", old_category="Support", new_category="Billing", actor="<@123>")` is called
- THEN the returned string contains "Support", "Billing", and "<@123>" with no unresolved `{...}` tokens
