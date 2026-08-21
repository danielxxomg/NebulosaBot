# Delta for Time Parsing

Cycle 2 of 3. Adds `parse_duration_strict` — a NEW strict variant in
`bot/utils/time.py` for the `,12h` ticket timer prefix. It adds `w` (weeks)
and `y` (years) units, uses strict regex anchoring
`^,\s*(\d+\s*[smhdwy])+$`, and MUST FAIL (return `None` / raise) on non-duration
input like `,hola` rather than the 3600 default. The existing `parse_duration`
(MUST NOT be merged with `timeparse.py`; different domain) is UNCHANGED —
`parse_duration_strict` is a separate function in the same module, not a
replacement.

## ADDED Requirements

### Requirement: parse_duration_strict strict duration parser

The system MUST provide `parse_duration_strict(text: str) -> int | None` in
`bot/utils/time.py`. It MUST match the leading comma-prefix strict regex
`^,\s*(\d+\s*[smhdwy])+$` (case-insensitive) and accept compound durations
(`12h`, `1d12h`, `2h 4h 6h 10h 1d 2d`, `1w`, `1y`). Supported units: `s`, `m`,
`h`, `d`, `w` (7d), `y` (365d). On a successful match it MUST return the total
seconds (summing each `(number)(unit)` pair). On any non-match — including
`,hola`, `,`, `12`, and `1x` — it MUST return `None` (or raise a documented
`ValueError`) and MUST NOT fall back to the 3600 default that
`parse_duration` uses. `parse_duration_strict` is a NEW function; it MUST NOT
replace or alias `parse_duration`.

#### Scenario: Parse hours

- GIVEN the input `,12h`
- WHEN `parse_duration_strict(",12h")` runs
- THEN it returns 43200

#### Scenario: Parse compound duration

- GIVEN the input `,1d12h`
- WHEN `parse_duration_strict(",1d12h")` runs
- THEN it returns 129600 (86400 + 43200)

#### Scenario: Parse weeks and years

- GIVEN the inputs `,1w` and `,1y`
- WHEN `parse_duration_strict` runs on each
- THEN it returns 604800 for `1w` and 31536000 for `1y`

#### Scenario: Parse space-separated alternatives list

- GIVEN the input `,2h 4h 6h 10h 1d 2d`
- WHEN `parse_duration_strict` runs
- THEN the total seconds sum all listed durations

#### Scenario: Non-duration input fails

- GIVEN the input `,hola`
- WHEN `parse_duration_strict(",hola")` runs
- THEN it returns `None` (or raises) and MUST NOT return 3600

#### Scenario: Missing comma fails

- GIVEN the input `12h` (no leading comma)
- WHEN `parse_duration_strict("12h")` runs
- THEN it returns `None` (strict anchor requires the comma prefix)

#### Scenario: Bare number fails

- GIVEN the input `,12`
- WHEN `parse_duration_strict(",12")` runs
- THEN it returns `None` (no unit)

#### Scenario: Unknown unit fails

- GIVEN the input `,1x`
- WHEN `parse_duration_strict(",1x")` runs
- THEN it returns `None`

### Requirement: time.py and timeparse.py stay separate and documented

`parse_duration_strict` MUST be added to `bot/utils/time.py` (the duration
domain). `bot/utils/time.py` (duration → seconds, now with both
`parse_duration` and `parse_duration_strict`) and `bot/utils/timeparse.py`
(DB timestamp → datetime) are DIFFERENT domains and MUST NOT be merged. The
module docstring in `time.py` MUST continue to state that `timeparse.py` is a
separate domain and they MUST NOT be merged; the same statement MUST remain in
`timeparse.py`. This delta MUST NOT introduce a re-export façade that collapses
the two modules.

#### Scenario: Both functions live in time.py, timeparse.py untouched

- GIVEN `bot/utils/time.py` and `bot/utils/timeparse.py` after the change
- WHEN the modules are inspected
- THEN `parse_duration` and `parse_duration_strict` both live in `time.py`, `timeparse.py` still parses DB timestamps, and no module re-exports one as the other

#### Scenario: Separation is documented

- GIVEN `bot/utils/time.py` and `bot/utils/timeparse.py`
- WHEN their module docstrings are read
- THEN each states the other is a separate domain and they MUST NOT be merged

## Scope boundary

This delta adds only `parse_duration_strict`. The `,12h` listener,
`ConfirmCancelView` reuse, `scheduledCloseAt`, the 60s loop, `,cancel`, and
`format_remaining` are specified in `ticket-service`, `ticket-model`,
`close-confirmation`, and `close-countdown`. Cycle 3
(voice/moderation, ScheduledAction, has_perm) is OUT OF SCOPE.
