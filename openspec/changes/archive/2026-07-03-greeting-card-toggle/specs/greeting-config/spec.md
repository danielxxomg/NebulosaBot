# Delta for Greeting Configuration

## ADDED Requirements

### Requirement: Welcome dispatch respects card toggle

`dispatch_welcome()` MUST check `config.welcome_card_enabled` before generating a greeting card. When `welcome_card_enabled` is `True`, the existing card-generation path is used. When `False`, only a text-only message is sent if `welcome_message` is non-empty; if `welcome_message` is also empty, nothing is sent.

#### Scenario: Welcome card sent when toggle enabled

- GIVEN `welcome_enabled` is `True`, `welcome_channel_id` is set, and `welcome_card_enabled` is `True`
- WHEN a member joins the guild
- THEN `ImageService.generate_greeting_card()` is called via `asyncio.to_thread` and the resulting `.png` file is sent to the welcome channel with optional text overlay

#### Scenario: Welcome text-only when toggle disabled and message set

- GIVEN `welcome_enabled` is `True`, `welcome_channel_id` is set, `welcome_card_enabled` is `False`, and `welcome_message` is non-empty
- WHEN a member joins the guild
- THEN a text-only message (formatted from `welcome_message` template) is sent to the welcome channel with no file attachment

#### Scenario: Welcome nothing when toggle disabled and no message

- GIVEN `welcome_enabled` is `True`, `welcome_channel_id` is set, `welcome_card_enabled` is `False`, and `welcome_message` is empty or null
- WHEN a member joins the guild
- THEN no message is sent to the welcome channel

### Requirement: Goodbye dispatch respects card toggle

`dispatch_goodbye()` MUST check `config.goodbye_card_enabled` before generating a greeting card. When `goodbye_card_enabled` is `True`, the existing card-generation path is used. When `False`, only a text-only message is sent if `goodbye_message` is non-empty; if `goodbye_message` is also empty, nothing is sent.

#### Scenario: Goodbye card sent when toggle enabled

- GIVEN `goodbye_enabled` is `True`, `goodbye_channel_id` is set, and `goodbye_card_enabled` is `True`
- WHEN a member leaves the guild
- THEN `ImageService.generate_greeting_card()` is called via `asyncio.to_thread` and the resulting `.png` file is sent to the goodbye channel with optional text overlay

#### Scenario: Goodbye text-only when toggle disabled and message set

- GIVEN `goodbye_enabled` is `True`, `goodbye_channel_id` is set, `goodbye_card_enabled` is `False`, and `goodbye_message` is non-empty
- WHEN a member leaves the guild
- THEN a text-only message (formatted from `goodbye_message` template) is sent to the goodbye channel with no file attachment

#### Scenario: Goodbye nothing when toggle disabled and no message

- GIVEN `goodbye_enabled` is `True`, `goodbye_channel_id` is set, `goodbye_card_enabled` is `False`, and `goodbye_message` is empty or null
- WHEN a member leaves the guild
- THEN no message is sent to the goodbye channel

### Requirement: Top-level greeting guard still applies

The `welcome_enabled` / `goodbye_enabled` top-level guards MUST be checked before the card toggle. When `welcome_enabled` is `False`, `dispatch_welcome()` MUST return immediately regardless of `welcome_card_enabled`. Same for goodbye.

#### Scenario: Welcome disabled at top level ignores card toggle

- GIVEN `welcome_enabled` is `False` and `welcome_card_enabled` is `True`
- WHEN a member joins the guild
- THEN no message or card is sent (dispatch returns early)
