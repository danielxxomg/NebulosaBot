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

### Requirement: RankRenderer extraction

The system MUST extract rank-card generation into a `RankRenderer` service
that owns `generate_rank_card`, the shared gradient loop, and the shared font
loader. Rank-card generation MUST NOT live in any legacy compatibility shim;
the shim module is deleted outright after the split.
The extracted `RankRenderer` MUST share the gradient loop and font loader
with the greeting renderer through a `shared_assets` module so neither
renderer duplicates that code. The extraction MUST NOT change the rank card
visual output.

#### Scenario: No legacy shim owns rank card generation

- GIVEN the repository tree after the split
- WHEN scanned for a rank-card-generating compatibility shim module
- THEN none exists; `generate_rank_card` lives only in `RankRenderer` under `bot/services/`

#### Scenario: Shared gradient and font loader are not duplicated

- GIVEN `RankRenderer` and the greeting renderer both need the gradient loop and font loader
- WHEN their imports are inspected
- THEN both import those helpers from a single `shared_assets` module, not from copy-pasted locals

#### Scenario: Rank card output is unchanged after the split

- GIVEN a member with fixed XP, level, and rank data
- WHEN `/rank` is invoked before and after the split
- THEN the two generated images are byte-identical (or visually identical under the existing visual-check scenario)

### Requirement: Non-blocking generation

The system MUST run rank card image generation outside the async event loop.
After the extraction, `RankRenderer.generate_rank_card` MUST be invoked via
`asyncio.to_thread` by its caller, consistent with the greeting renderer.

#### Scenario: Concurrent requests

- GIVEN many members request /rank simultaneously
- WHEN the images are generated
- THEN the bot remains responsive and no event-loop blocking occurs

#### Scenario: Generation runs in a worker thread

- GIVEN a rank card is requested
- WHEN `RankRenderer.generate_rank_card` executes
- THEN the Pillow work runs in a thread via `asyncio.to_thread`, not on the event loop

### Requirement: Avatar handling

The system SHOULD fall back to a default avatar or placeholder if the member's
avatar cannot be fetched. After the extraction, the avatar-fetch and
circular-paste helpers MUST live in `shared_assets` and be shared with the
greeting renderer; the fallback MUST remain non-breaking.

#### Scenario: Missing avatar

- GIVEN member A has no avatar
- WHEN /rank is invoked
- THEN the card renders with a default placeholder image

#### Scenario: Avatar helpers are shared

- GIVEN `RankRenderer` and the greeting renderer both paste a circular avatar
- WHEN their helper usage is inspected
- THEN both call the shared `_paste_circular_asset` / `_safe_fetch_avatar` from `shared_assets`, not duplicated copies
