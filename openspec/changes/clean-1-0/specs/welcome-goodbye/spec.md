# Delta for Welcome/Goodbye

## ADDED Requirements

### Requirement: Setup-module configuration parity and preview

Welcome and goodbye configuration MUST be fully manageable through the `/setup` panel modules, producing the SAME persisted state and cache invalidation as the deleted command groups. Each module MUST provide a test button that renders and delivers a REAL preview (localized card + message content) to the configured channel. Preview delivery failures (missing/inaccessible channel) MUST surface an ephemeral panel error without mutating config.

#### Scenario: Module save matches legacy command effect

- GIVEN the Welcome module sets channel #general and enables welcome
- WHEN the admin saves
- THEN `welcome_channel_id` is updated AND the cache entry is invalidated exactly as the old `/welcome channel` command did

#### Scenario: Test button sends real preview

- GIVEN a guild with language `es` and a welcome channel configured
- WHEN the admin presses the Welcome test button
- THEN a real Spanish welcome card is delivered to the configured channel

#### Scenario: Preview failure is ephemeral and safe

- GIVEN no welcome channel is configured
- WHEN the test button is pressed
- THEN an ephemeral error explains the missing channel and no message is sent anywhere

## MODIFIED Requirements

### Requirement: Localized greeting card text

The system MUST render greeting card title and member-count text in the guild's configured language by receiving pre-translated strings from the caller. Card generation MUST NOT contain hardcoded greeting copy. Spanish (`es`) and English (`en`) outputs MUST be independently testable.

(Previously: `/welcome test` / `/goodbye test` commands exercised localized rendering; previews now come exclusively from the setup-panel module test buttons.)

#### Scenario: Spanish welcome card

- GIVEN a guild configured with language `es` and welcome card enabled
- WHEN a member joins and the card is generated
- THEN the title uses the Spanish welcome string and the count uses the Spanish member-count string with the member number interpolated

#### Scenario: English goodbye card

- GIVEN a guild configured with language `en` and goodbye card enabled
- WHEN a member leaves and the card is generated
- THEN the title uses the English goodbye string and the count uses the English member-count string

#### Scenario: Caller passes translated strings

- GIVEN `GreetingService` resolves the guild language via `t()`
- WHEN `generate_greeting_card()` is invoked
- THEN the rendered card uses the `greeting_title` and `member_count_text` arguments supplied by the caller, not hardcoded English

## REMOVED Requirements

### Requirement: Welcome config command group

(Reason: replaced by the `/setup` Welcome module — command-surface consolidation into the panel; orphan columns (`cardEnabled`, `themeId`, `onboardingChannelId`) become editable there.)
(Migration: use `/setup` → Welcome module for channel, toggle, message template, theme, card-enabled, and onboarding-channel settings.)

### Requirement: Goodbye config command group

(Reason: replaced by the `/setup` Goodbye module — same consolidation.)
(Migration: use `/setup` → Goodbye module for channel, toggle, and message template settings.)
