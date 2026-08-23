# Delta for i18n-system

## ADDED Requirements

### Requirement: Translation key coverage test

An automated test MUST statically scan `bot/` sources for literal translation keys passed to `t()` and assert every such key exists in BOTH `es.json` and `en.json`. Dynamically composed keys MUST be exempted exclusively via a module-level `DYNAMIC_KEY_PATTERNS` allowlist of regex patterns (e.g. covering `tickets.timer.unit_*` and `ocio.8ball.r\d+`); each allowlist entry MUST correspond to a genuinely dynamic key family. A violation MUST fail with a single consolidated report listing every missing key together with its callsite `file:line`. Unused-key detection is advisory only (it MUST NOT fail the suite).

#### Scenario: Missing static key fails with callsite

- GIVEN a literal `t(guild, "some.missing.key")` call in `bot/` and the key absent from a locale file
- WHEN the coverage test runs
- THEN it fails listing `some.missing.key` with the originating file and line

#### Scenario: Dynamic keys do not false-fail

- GIVEN a runtime composition such as `f"tickets.timer.unit_{unit}"` matches a `DYNAMIC_KEY_PATTERNS` entry
- WHEN the scanner encounters the composition site
- THEN no failure is raised for that dynamic key family

#### Scenario: Both locales must agree

- GIVEN a literal key exists in `es.json` but not `en.json`
- WHEN the coverage test runs
- THEN it fails (both locales are required for every literal key)

### Requirement: Ticket timer locale keys

Both locale files MUST gain the `tickets.timer.*` namespace used by the scheduled-close flow — including its title/body strings and the `unit_second` through `unit_day` units interpolated via `{unit}` — so users never see raw keys. The locale files MUST gain ONLY these new keys plus the eight-ball title key below; existing keys, JSON structure, and translations MUST remain untouched.

#### Scenario: Timer keys resolve in both locales

- GIVEN `es.json` and `en.json`
- WHEN `t(guild, "tickets.timer.scheduled_title")` and the unit keys resolve
- THEN non-empty localized strings return from both locales with `{unit}` interpolating correctly

#### Scenario: Raw keys never reach users

- GIVEN the scheduled-close flow renders its embeds
- WHEN any timer string is resolved
- THEN no raw `tickets.timer.` key appears in user-visible output

### Requirement: Eight-ball embed title key

Both locale files MUST gain `ocio.8ball.embed_title`. The existing `ocio.8ball.r1`–`r20` responses and all other existing translations MUST remain byte-for-byte unchanged.

#### Scenario: Title resolves in both locales

- GIVEN `es.json` and `en.json`
- WHEN `t(guild, "ocio.8ball.embed_title")` is called
- THEN a non-empty localized title returns from both locales

#### Scenario: Existing translations untouched

- GIVEN the new keys are added to both locale files
- WHEN any pre-existing key is compared against its prior value
- THEN every pre-existing key and structure is unchanged
