# Ocio Commands Specification

## Purpose

Provide casual, fun interactions for guild members through simple games and random outcomes.

## Requirements

### Requirement: Dice command

The `/dice` command MUST roll a die and return a result between 1 and the requested number of sides. The command is RENAMED from `/dados` to canonical English `/dice`, with Spanish `name_localizations` (`es: "dados"`). `/dados` MUST NOT resolve in the default locale.

#### Scenario: Default six-sided roll

- GIVEN a member invokes `/dice` without arguments
- WHEN it executes
- THEN the bot replies with a result in [1, 6]

#### Scenario: Custom sides roll

- GIVEN sides between 2 and 100
- WHEN `/dice` executes
- THEN the result is in [1, sides]

#### Scenario: Out-of-range sides

- GIVEN sides below 2 or above 100
- WHEN `/dice` executes
- THEN the input is rejected with an error embed

#### Scenario: Spanish localization preserved

- GIVEN client locale `es`
- WHEN the command list renders
- THEN it shows "dados"; under `en`, "dice"

### Requirement: Banana command

The `/banana` command MUST reply with a banana image and a random measurement. The image comes from 5–8 `.webp` variants in `assets/images/banana/*.webp` via `OcioService.get_random_banana()`. Normal measurement range: [2, 30] cm. A 1% "dorada" easter egg returns 30 cm. Missing/corrupt pool asset MUST fall back to a Pillow placeholder so delivery succeeds. The response is PERMANENT (visible to all) and MUST NOT write to the database.

#### Scenario: Normal banana from pool

- GIVEN the pool has 6 variants and the 99% path runs
- WHEN `get_random_banana()` executes
- THEN the permanent reply carries a pool image and measurement in [2, 30]

#### Scenario: Dorada easter egg

- GIVEN the 1% dorada path is selected
- WHEN it runs
- THEN the reply shows the dorada variant at 30 cm

#### Scenario: Missing pool asset falls back to Pillow

- GIVEN the selected variant is missing or corrupt
- WHEN `/banana` executes
- THEN a Pillow placeholder attaches and delivery succeeds

#### Scenario: Empty pool falls back to Pillow

- GIVEN `assets/images/banana/` has zero `.webp` files
- WHEN `/banana` executes
- THEN a Pillow placeholder is attached and delivery succeeds

#### Scenario: Banana writes no DB row

- GIVEN an invocation
- WHEN it executes
- THEN no table row is inserted, updated, or deleted

#### Scenario: Banana is permanent

- GIVEN an invocation
- WHEN it executes
- THEN the reply is a permanent channel message

### Requirement: OcioService service layer

The system MUST provide an `OcioService` in the services layer that owns
non-Discord logic: `get_random_banana()` (pool pick + 1% dorada weight +
fallback) and `get_8ball_response()` (20-response pick, i18n). The cog MUST be
thin (Discord I/O only) and delegate to `OcioService`. `OcioService` MUST be
unit-testable without Discord mocks. Pillow work (the fallback render) MUST
run via `asyncio.to_thread`.

#### Scenario: OcioService is unit-testable without Discord

- GIVEN `OcioService.get_random_banana()` and `get_8ball_response()`
- WHEN unit tests call them directly
- THEN no Discord object (Member, Interaction, Guild) is required and the results are deterministic given the RNG

#### Scenario: Pillfallback runs off the event loop

- GIVEN the Pillow banana fallback render is triggered
- WHEN the render executes
- THEN the Pillow work runs in a thread via `asyncio.to_thread`, not on the event loop

### Requirement: 8ball command

The system MUST provide a `/8ball` pure app command returning one of 20 localized responses (`t()`, es/en) to a yes/no question, chosen uniformly at random. The embed title MUST use localized `ocio.8ball.embed_title` — never a raw key. The response is PERMANENT and MUST NOT write to the database.

#### Scenario: Localized response in Spanish guild

- GIVEN a member asks in a Spanish guild
- WHEN `/8ball` executes
- THEN one of the 20 Spanish `ocio.8ball.*` responses replies permanently

#### Scenario: Title localized, no raw key

- GIVEN es and en guilds invoke `/8ball`
- WHEN embeds render
- THEN titles come from `ocio.8ball.embed_title` per guild language

#### Scenario: 8ball writes no DB row

- GIVEN an invocation
- WHEN it executes
- THEN no table row is inserted, updated, or deleted

#### Scenario: 8ball is permanent

- GIVEN an invocation
- WHEN it executes
- THEN the reply is a permanent channel message

### Requirement: Ocio commands cooldown and handler

`/dice`, `/banana`, and `/8ball` MUST each carry `@app_commands.checks.cooldown(1, 5, BucketType.user)` (1 use per 5 seconds per user). A `CommandOnCooldown` handler MUST reply ephemerally with `retry_after` formatted via `t()`; it MUST NOT raise or leak a traceback.

#### Scenario: Cooldown blocks and localizes

- GIVEN `/banana` was just invoked
- WHEN invoked again immediately
- THEN the handler replies ephemerally with the localized retry-after message

#### Scenario: Cooldown releases after 5s

- GIVEN the last invocation was 5s ago
- WHEN invoked again
- THEN it executes normally
