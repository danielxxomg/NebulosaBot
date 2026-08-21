# Delta for Ocio Commands

Cycle 2 of 3. Upgrades `/banana` to a pool of 5–8 `.webp` variants with a 1%
"dorada 30cm" easter egg and a Pillow fallback, adds a `/8ball` command with
20 i18n responses, and adds a shared `@cooldown(1, 5, BucketType.user)` plus a
`CommandOnCooldown` handler with `retry_after` + `t()`. All ocio commands are
ephemeral where appropriate and MUST NOT write to the database. Logic is
extracted to a testable `OcioService` (services layer; no Discord mocks needed
for unit tests per the architecture rule).

## ADDED Requirements

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

The system MUST provide a `/8ball` hybrid command that returns one of 20
localized responses (Spanish and English, via `t()`) to a yes/no question. The
response MUST be chosen uniformly at random from the 20-key set. The command
MUST be ephemeral and MUST NOT write to the database.

#### Scenario: 8ball returns a localized response

- GIVEN a member invokes `/8ball` with a question in a Spanish guild
- WHEN the command executes
- THEN the bot replies ephemerally with one of the 20 Spanish `ocio.8ball.*` responses

#### Scenario: 8ball is i18n-isolated

- GIVEN the 20-key `ocio.8ball.*` set exists in `es.json` and `en.json`
- WHEN an English-guild member invokes `/8ball`
- THEN the reply uses the English set and Spanish and English outputs are independently testable

#### Scenario: 8ball writes no DB row

- GIVEN a member invokes `/8ball`
- WHEN the command executes
- THEN no row is inserted, updated, or deleted in any table

### Requirement: Ocio commands cooldown and handler

`/dados`, `/banana`, and `/8ball` MUST each carry
`@commands.cooldown(1, 5, BucketType.user)` (1 use per 5 seconds per user). The
cog MUST provide a `CommandOnCooldown` error handler that, on cooldown,
replies ephemerally with `retry_after` formatted via `t()` (localized). The
handler MUST NOT raise or surface a raw traceback.

#### Scenario: Cooldown blocks second invocation within 5s

- GIVEN a member invokes `/banana` and immediately invokes `/banana` again
- WHEN the second invocation is processed
- THEN `CommandOnCooldown` is raised and the handler replies ephemerally with the localized retry-after message

#### Scenario: Cooldown releases after 5s

- GIVEN a member invoked `/banana` 5 seconds ago
- WHEN the member invokes `/banana` again
- THEN the command executes normally

## MODIFIED Requirements

### Requirement: Banana command

The `/banana` command MUST reply with a banana image and a random measurement. The image MUST be selected from a pool of 5–8 `.webp` variants in `assets/images/banana/*.webp` via `OcioService.get_random_banana()`. The measurement MUST be in the range [2, 30] cm for a normal banana. A 1% "dorada" easter egg MUST return a 30 cm measurement (the dorada variant). If the selected pool asset is missing or corrupt, the command MUST fall back to a Pillow-rendered placeholder so delivery still succeeds. The command MUST be ephemeral and MUST NOT write to the database.
(Previously: the command loaded a single `assets/images/banana.webp` and returned a measurement in [2, 30]; no pool, no dorada easter egg, no fallback, and no no-DB/ephemeral contract.)

#### Scenario: Normal banana from pool

- GIVEN a member invokes `/banana` and the pool has 6 `.webp` variants
- WHEN `OcioService.get_random_banana()` runs (99% path)
- THEN the reply contains an image attachment loaded from one of `assets/images/banana/*.webp` and a measurement in [2, 30] cm

#### Scenario: Dorada easter egg

- GIVEN a member invokes `/banana` and the 1% dorada path is selected
- WHEN `OcioService.get_random_banana()` runs
- THEN the reply contains the dorada variant and a 30 cm measurement

#### Scenario: Missing pool asset falls back to Pillow

- GIVEN the selected `assets/images/banana/<variant>.webp` is missing or corrupt
- WHEN `/banana` executes
- THEN a Pillow-rendered placeholder is attached and delivery succeeds (no error embed)

#### Scenario: Empty pool falls back to Pillow

- GIVEN `assets/images/banana/` has zero `.webp` files
- WHEN `/banana` executes
- THEN a Pillow placeholder is attached and delivery succeeds

#### Scenario: Banana writes no DB row

- GIVEN a member invokes `/banana`
- WHEN the command executes
- THEN no row is inserted, updated, or deleted in any table

#### Scenario: Banana is ephemeral

- GIVEN a member invokes `/banana`
- WHEN the command executes
- THEN the reply is ephemeral

## Scope boundary

This delta adds the banana pool + dorada + fallback, `/8ball`, `OcioService`,
and the cooldown + handler. The dice command (`/dados`) is unchanged except
for the shared cooldown. Cycle 3 (voice/moderation, ScheduledAction, has_perm)
is OUT OF SCOPE. `bot/utils/time.py` and `bot/utils/timeparse.py` MUST NOT be
merged.
