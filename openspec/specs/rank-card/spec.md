# Rank Card Specification

## Purpose

Define the visual and behavioral requirements for the generated member rank card image.

## Requirements

### Requirement: Rank card composition

The system MUST generate a rank card image showing the member's circular avatar, username, current level, rank number, total XP, XP needed for the next level, and an XP progress bar.

#### Scenario: Generate for existing member

- GIVEN member A has XP, level, and rank data
- WHEN /rank is invoked
- THEN the generated image contains all required elements

#### Scenario: New member card

- GIVEN member A has 0 XP and level 0
- WHEN /rank is invoked
- THEN the generated image shows level 0 and an empty XP bar

### Requirement: Visual style

The system MUST render the rank card with a dark gradient background, light text, and a colored XP progress bar.

#### Scenario: Visual check

- GIVEN a rank card is generated
- THEN the background is a dark gradient, the avatar is circular, and the XP bar shows progress from 0% to 100%

### Requirement: Non-blocking generation

The system MUST run rank card image generation outside the async event loop.

#### Scenario: Concurrent requests

- GIVEN many members request /rank simultaneously
- WHEN the images are generated
- THEN the bot remains responsive and no event-loop blocking occurs

### Requirement: Avatar handling

The system SHOULD fall back to a default avatar or placeholder if the member's avatar cannot be fetched.

#### Scenario: Missing avatar

- GIVEN member A has no avatar
- WHEN /rank is invoked
- THEN the card renders with a default placeholder image
