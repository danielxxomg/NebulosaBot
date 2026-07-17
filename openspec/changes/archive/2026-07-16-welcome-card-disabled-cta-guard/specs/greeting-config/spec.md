# Delta for greeting-config

Guards the disabled-welcome-card path: it must never emit CTA-only content and never let CTA-channel failures block non-empty text. The canonical main spec is not modified this phase; this delta clarifies and extends the existing card-toggle requirement.

## ADDED Requirements

### Requirement: Global welcome guard is authoritative

`welcome_enabled` MUST be evaluated before card-toggle and CTA logic. When `False`, `dispatch_welcome()` MUST send no message, card, or CTA regardless of `welcome_card_enabled`, `welcome_message`, or `onboarding_channel_id`.

#### Scenario: Globally disabled ignores card toggle and message

- GIVEN `welcome_enabled` False, `welcome_card_enabled` True, welcome channel set, `welcome_message` non-empty
- WHEN a member joins
- THEN no message or card is sent

#### Scenario: Globally disabled ignores resolvable CTA

- GIVEN `welcome_enabled` False and `onboarding_channel_id` resolves
- WHEN a member joins
- THEN no CTA or message is sent

### Requirement: Whitespace normalization for welcome text emptiness

For the card-disabled text path, `welcome_message` is empty when it is `None`, an empty string, or whitespace-only. Emptiness MUST be decided on the **formatted** content: format the template via the standard localization and variable-replacement pipeline, then strip leading/trailing whitespace (spaces, tabs, newlines, carriage returns); the message is empty iff the stripped result is `None` or a zero-length string. A bare truthiness check on the raw template MUST NOT be the emptiness gate, because a template that becomes whitespace-only after variable substitution MUST be treated as empty.

#### Scenario: None message is empty

- GIVEN `welcome_enabled` True, `welcome_card_enabled` False, `welcome_message` `None`
- WHEN a member joins and the card-disabled text path runs
- THEN no message is sent, even when `onboarding_channel_id` resolves

#### Scenario: Empty-string message is empty

- GIVEN `welcome_enabled` True, `welcome_card_enabled` False, `welcome_message` `""`
- WHEN a member joins and the card-disabled text path runs
- THEN no message is sent, even when `onboarding_channel_id` resolves

#### Scenario: Whitespace-only message is empty

- GIVEN `welcome_enabled` True, `welcome_card_enabled` False, `welcome_message` `"   \n\t "`
- WHEN a member joins and the card-disabled text path runs
- THEN the stripped formatted content is zero-length and no message is sent

#### Scenario: Template becoming whitespace-only after formatting is empty

- GIVEN `welcome_enabled` True, `welcome_card_enabled` False, `welcome_message` `" {member_nick} "`, member nick resolves to empty
- WHEN a member joins and the card-disabled text path runs
- THEN the formatted `"  "` strips to zero-length and no message is sent

### Requirement: Disabled card text-only path isolates CTA resolution

When `welcome_card_enabled` is `False` and the normalized message is non-empty, the system MUST send exactly the formatted text-only message and MUST NOT append, prepend, or substitute any CTA. It MUST NOT call the CTA resolver on this path and MUST NOT send a CTA-only message. Invalid, missing, or inaccessible `onboarding_channel_id` MUST NOT block, alter, or suppress the non-empty text-only message.

#### Scenario: Non-empty message sends text only, no CTA

- GIVEN `welcome_enabled` True, `welcome_card_enabled` False, `welcome_message` non-empty, `onboarding_channel_id` resolvable
- WHEN a member joins
- THEN exactly one text-only message is sent with no attachment and no CTA suffix

#### Scenario: Invalid CTA channel does not block non-empty text

- GIVEN `welcome_enabled` True, `welcome_card_enabled` False, `welcome_message` non-empty, `onboarding_channel_id` invalid/inaccessible
- WHEN a member joins
- THEN exactly one text-only message is sent and no CTA is sent

#### Scenario: Missing CTA channel does not block non-empty text

- GIVEN `welcome_enabled` True, `welcome_card_enabled` False, `welcome_message` non-empty, `onboarding_channel_id` `None`
- WHEN a member joins
- THEN exactly one text-only message is sent

### Requirement: Disabled card silence when message is empty

When `welcome_card_enabled` is `False` and the normalized message is empty, the system MUST send nothing regardless of `onboarding_channel_id` validity, accessibility, or resolution. An empty card-disabled message MUST NOT produce a CTA-only message.

#### Scenario: Empty message sends nothing despite resolvable CTA

- GIVEN `welcome_enabled` True, `welcome_card_enabled` False, `welcome_message` empty/whitespace-only, `onboarding_channel_id` resolvable
- WHEN a member joins
- THEN no message, card, or CTA is sent

#### Scenario: Empty message sends nothing despite invalid CTA

- GIVEN `welcome_enabled` True, `welcome_card_enabled` False, `welcome_message` empty, `onboarding_channel_id` invalid/inaccessible
- WHEN a member joins
- THEN nothing is sent

### Requirement: Localization and formatting preserved for text-only welcomes

The card-disabled text path MUST preserve the localization, variable replacement, and template formatting used by the card-enabled path for non-empty messages. CTA suppression and emptiness normalization MUST NOT alter token substitution, locale selection, or formatting of the sent payload.

#### Scenario: Localization applied to non-empty text-only message

- GIVEN `welcome_enabled` True, `welcome_card_enabled` False, `welcome_message` a localized template with member variables
- WHEN a member joins
- THEN the sent message uses the resolved locale and replaces member variables as the card-enabled path would

### Requirement: Card-enabled CTA behavior preserved

The card-enabled path (`welcome_card_enabled` True) MUST remain unchanged. The existing CTA-only exception — card-enabled welcome with an empty template and a resolvable onboarding channel producing a CTA-only message — MUST continue to hold. CTA resolution, composition, and the resolver MUST NOT be modified for the card-enabled path.

#### Scenario: Card enabled with empty message and resolvable CTA is CTA-only

- GIVEN `welcome_enabled` True, `welcome_card_enabled` True, `welcome_message` empty, `onboarding_channel_id` resolvable
- WHEN a member joins
- THEN a CTA-only message is sent

#### Scenario: Card enabled with message appends localized CTA

- GIVEN `welcome_enabled` True, `welcome_card_enabled` True, `welcome_message` non-empty, `onboarding_channel_id` resolvable
- WHEN a member joins
- THEN a greeting card with the formatted message and a localized CTA suffix is sent

### Requirement: No migration, no new configuration, no user-facing notice

This change MUST be automatic and silent for existing guilds. It MUST NOT introduce migrations, new configuration or environment fields, or user-facing notices. CTA suppression on the card-disabled text path MUST require no opt-in or admin action.

#### Scenario: Existing persisted rows remain runtime-compatible

- GIVEN a pre-change `greeting_config` row that omits fields introduced by this change and an existing guild configuration
- WHEN `GreetingService` loads the row and dispatches the welcome
- THEN the row remains readable with existing defaults, no greeting-config write occurs, no migration/config field is required by the service, and no user-facing notice is emitted

#### Scenario: CTA suppression is silent with no admin notice

- GIVEN an existing guild with `welcome_card_enabled` False, empty `welcome_message`, resolvable `onboarding_channel_id`
- WHEN the change is deployed and a member joins
- THEN the bot silently sends nothing and emits no user-facing notice

### Requirement: Bounded static typing cleanup with no runtime impact

The change MUST resolve exactly the eight pre-existing mypy diagnostics: seven in `bot/services/greeting_service.py` (channel narrowing, explicit annotations, and removed/moved inaccurate unused ignores) plus the generic `Command` type-argument diagnostic at `bot/core/i18n.py:294`. The cleanup MUST be limited to explicit type annotations, safe Discord channel narrowing, and removing/moving inaccurate unused ignores; it MUST NOT alter runtime behavior, control flow, or sent payloads. The cleanup MUST NOT perform broad type changes across the codebase or touch unrelated files. Running the focused mypy command `uv run mypy bot/services/greeting_service.py` MUST produce no diagnostics, and because mypy follows imports, this MUST include the `bot/core/i18n.py:294` diagnostic surfaced through the service.

#### Scenario: Focused mypy is clean including imported i18n diagnostic

- GIVEN the eight pre-existing mypy diagnostics are unresolved
- WHEN `uv run mypy bot/services/greeting_service.py` is run after the bounded cleanup
- THEN the command exits with no diagnostics and the `bot/core/i18n.py:294` generic `Command` diagnostic is also clear

#### Scenario: Bounded cleanup preserves runtime behavior and full test safety

- GIVEN the cleanup edits only annotations, safe channel narrowing, and unused ignores in `bot/services/greeting_service.py` and the single `Command` annotation at `bot/core/i18n.py:294`
- WHEN `uv run pytest tests/test_greeting_service.py -v --no-cov` and `uv run pytest` are run
- THEN the guard and full suite pass exactly as before, no sent payload or control-flow changes occur, and no unrelated file is modified
