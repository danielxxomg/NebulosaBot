# Delta for i18n-system

## ADDED Requirements

### Requirement: Greeting card and CTA locale keys

The system MUST provide greeting card and welcome CTA locale keys in both `es.json` and `en.json` under the `greetings.card.*` and `greetings.cta.*` namespaces. Keys MUST include a welcome title, a goodbye title, a member-count string, and a welcome onboarding CTA string. Spanish and English values MUST be independently resolvable via `t()`.

#### Scenario: Spanish card keys resolvable

- GIVEN `es.json` contains `greetings.card.welcome_title`, `greetings.card.goodbye_title`, and `greetings.card.member_count`
- WHEN `t(guild_id, "greetings.card.welcome_title")` is called for a Spanish guild
- THEN a non-empty Spanish string is returned

#### Scenario: English card keys resolvable

- GIVEN `en.json` contains the `greetings.card.*` keys
- WHEN `t(guild_id, "greetings.card.member_count", count=42)` is called for an English guild
- THEN a non-empty English string with `42` interpolated is returned

#### Scenario: Member count placeholder interpolation

- GIVEN `greetings.card.member_count` contains a `{count}` placeholder
- WHEN `t(guild_id, "greetings.card.member_count", count=7)` is called
- THEN the returned string contains `7` and no unresolved `{...}` tokens

#### Scenario: Welcome CTA keys resolvable with channel placeholder

- GIVEN `greetings.cta.welcome_onboarding` contains a `{channel}` placeholder
- WHEN `t(guild_id, "greetings.cta.welcome_onboarding", channel="<#123>")` is called
- THEN the returned string contains the channel mention and no unresolved `{...}` tokens

#### Scenario: Distinct placeholder namespace

- GIVEN the `greetings` namespace uses `{count}` and `{channel}` placeholders
- WHEN greeting templates use `{mention}`, `{user}`, and `{server}`
- THEN the greeting-card placeholders (`{count}`, `{channel}`) do not collide with the message-template placeholders

#### Scenario: Fallback chain still applies to greeting keys

- GIVEN a guild configured with language `en` and `greetings.card.welcome_title` exists only in `es.json`
- WHEN `t(guild_id, "greetings.card.welcome_title")` is called
- THEN the system falls back to the Spanish value before returning the raw key
