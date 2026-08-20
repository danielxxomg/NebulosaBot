# Delta for Rank Card

Cycle 1. Extracts rank-card generation out of the 454-line `ImageService`
into a dedicated `RankRenderer` (SRP). This is the rank-side counterpart to the
greeting-side `GreetingRenderer` split. No visual or behavioral change to the
rank card; only ownership moves.

## ADDED Requirements

### Requirement: RankRenderer extraction

The system MUST extract rank-card generation into a `RankRenderer` service
that owns `generate_rank_card`, the shared gradient loop, and the shared font
loader. `ImageService` MUST NOT own rank-card generation after the split.
The extracted `RankRenderer` MUST share the gradient loop and font loader
with the greeting renderer through a `shared_assets` module so neither
renderer duplicates that code. The extraction MUST NOT change the rank card
visual output.

#### Scenario: ImageService no longer owns rank card

- GIVEN `bot/services/image_service.py` after the split
- WHEN scanned for `generate_rank_card`
- THEN it is absent; the method lives in `RankRenderer` under `bot/services/`

#### Scenario: Shared gradient and font loader are not duplicated

- GIVEN `RankRenderer` and the greeting renderer both need the gradient loop and font loader
- WHEN their imports are inspected
- THEN both import those helpers from a single `shared_assets` module, not from copy-pasted locals

#### Scenario: Rank card output is unchanged after the split

- GIVEN a member with fixed XP, level, and rank data
- WHEN `/rank` is invoked before and after the split
- THEN the two generated images are byte-identical (or visually identical under the existing visual-check scenario)

## MODIFIED Requirements

### Requirement: Non-blocking generation

The system MUST run rank card image generation outside the async event loop.
After the extraction, `RankRenderer.generate_rank_card` MUST be invoked via
`asyncio.to_thread` by its caller, consistent with the greeting renderer.

(Previously: the requirement held but did not name the owning class; generation
lived in `ImageService`.)

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

(Previously: the fallback existed but the helpers were private to
`ImageService`.)

#### Scenario: Missing avatar

- GIVEN member A has no avatar
- WHEN /rank is invoked
- THEN the card renders with a default placeholder image

#### Scenario: Avatar helpers are shared

- GIVEN `RankRenderer` and the greeting renderer both paste a circular avatar
- WHEN their helper usage is inspected
- THEN both call the shared `_paste_circular_asset` / `_safe_fetch_avatar` from `shared_assets`, not duplicated copies

## Scope boundary

This delta is the rank-side SRP split only. Cycle 2 (Neon SVG rank card),
Cycle 3 (timer, 12h, banana, RLS, voice/moderation, ScheduledAction, has_perm),
and any visual redesign of the rank card are OUT OF SCOPE.
