# Proposal: Localized, Branded Welcome and Goodbye UX

## Intent

`ImageService` hardcodes English card text and receives no guild language. The verified active greeting guild is Spanish, making the configured experience inconsistent and non-actionable. This change makes welcome and goodbye coherent and branded.

## Scope

### In Scope
- Localize card titles and member-count text in Spanish and English, including test cards.
- Refresh both cards with guild identity, member avatar/name/count, hierarchy, accent treatment, and safe asset fallbacks.
- Keep the banner focused on identity/greeting; add a brief CTA in the message content to a configurable start/onboarding channel. A custom administrator message MUST NOT remove that CTA.
- Persist and expose an optional onboarding channel through greeting configuration.

### Out of Scope
- Unrelated command, ticket, moderation, dashboard, or broad i18n cleanup.
- New onboarding flows, analytics, or a full card redesign beyond the scoped visual treatment.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `welcome-goodbye`: localized, branded cards and welcome CTA behavior for join/leave delivery.
- `greeting-config`: optional configurable onboarding/start channel and cache-safe persistence.
- `i18n-system`: greeting-card and CTA keys in `en.json` and `es.json`.

## Approach

Resolve translations in `GreetingService` with `t()` and pass strings plus identity inputs to the pure Pillow renderer. Extend `GreetingConfig`, `bot/core/db/greeting_db.py`, a Supabase migration, and the configuration surface for the nullable CTA channel. Preserve cache-first reads and Realtime invalidation. Test locale resolution, custom-message-plus-CTA behavior, and fallbacks.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `bot/services/image_service.py` | Modified | Localized, branded rendering. |
| `bot/services/greeting_service.py` | Modified | Locale resolution and CTA dispatch. |
| `bot/models/greeting_config.py`, `bot/core/db/greeting_db.py`, `migrations/` | Modified/New | Persist CTA channel. |
| `bot/locales/{en,es}.json`, `bot/cogs/greetings.py`, `dashboard/` | Modified | Locale keys, tests, and configuration. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Missing assets or inaccessible CTA channel interrupt delivery | Med | Nullable inputs, fallbacks, and non-fatal CTA omission. |
| Locale/layout or schema regression | Low | Bounded copy, focused tests, additive nullable migration. |

## Rollback Plan

Revert application, locale, dashboard, and migration changes; restore the renderer contract and disable CTA composition. Existing rows remain valid.

## Dependencies

- Existing guild-language registration, Realtime CDC, and greeting configuration.
- Verification expectation: `uv run pytest`.

## Success Criteria

- [ ] Spanish and English dispatch/test cards use localized title and count strings with no hardcoded card copy.
- [ ] Welcome messages include the configured onboarding CTA even when a custom message exists; missing targets do not break delivery.
- [ ] Both cards retain member identity/count and guild treatment, with asset failures handled safely.
- [ ] Focused tests pass for localization, CTA composition, migration compatibility, and fallbacks.
