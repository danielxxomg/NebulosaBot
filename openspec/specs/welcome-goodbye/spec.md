# Welcome/Goodbye Specification

## Purpose

Generate and dispatch welcome/goodbye greeting cards on member join and leave events.

## Requirements

### Requirement: Welcome card on join

The system MUST send a welcome card to `welcome_channel_id` when `welcome_card_enabled` is true.

#### Scenario: Member joins guild

- GIVEN `welcome_card_enabled` is true and `welcome_channel_id` is set
- WHEN a member joins the guild
- THEN a welcome card image is generated and sent to the welcome channel

#### Scenario: Welcome disabled

- GIVEN `welcome_card_enabled` is false
- WHEN a member joins the guild
- THEN no welcome card is sent

### Requirement: Goodbye card on leave

The system MUST send a goodbye card to `goodbye_channel_id` when `goodbye_card_enabled` is true.

#### Scenario: Member leaves guild

- GIVEN `goodbye_card_enabled` is true and `goodbye_channel_id` is set
- WHEN a member leaves the guild
- THEN a goodbye card image is generated and sent to the goodbye channel

### Requirement: Card generation

The system MUST generate greeting cards using `ImageService.generate_greeting_card()` with the dark gradient style, member avatar, username, and guild name.

#### Scenario: Generate welcome card

- GIVEN a member and guild
- WHEN `generate_greeting_card()` is invoked with type `welcome`
- THEN the returned image contains the dark gradient background, circular avatar, and greeting text

#### Scenario: Missing avatar

- GIVEN a member has no avatar
- WHEN the card is generated
- THEN a default placeholder avatar is rendered

### Requirement: Missing channel guard

The system MUST skip sending a greeting card when the configured channel is null or inaccessible.

#### Scenario: Welcome channel missing

- GIVEN `welcome_channel_id` is null
- WHEN a member joins the guild
- THEN no card is sent and no error is surfaced
