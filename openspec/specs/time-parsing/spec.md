# Time Parsing Specification

## Purpose

Parse human-readable duration strings into seconds for moderation timeouts and mutes.

## Requirements

### Requirement: Parse single-unit duration

The system MUST parse a duration string consisting of a number and a single unit suffix into seconds.

#### Scenario: Parse hours

- GIVEN the input "1h"
- WHEN the parser runs
- THEN it returns 3600

#### Scenario: Parse minutes

- GIVEN the input "30m"
- WHEN the parser runs
- THEN it returns 1800

#### Scenario: Parse days

- GIVEN the input "2d"
- WHEN the parser runs
- THEN it returns 172800

### Requirement: Handle invalid duration

The system MUST return a default of 3600 seconds (1 hour) for duration strings that do not match the supported format.

#### Scenario: Missing unit

- GIVEN the input "30"
- WHEN the parser runs
- THEN it returns 3600

#### Scenario: Unknown unit

- GIVEN the input "1x"
- WHEN the parser runs
- THEN it returns 3600

### Requirement: Handle zero and empty durations

The system MUST return a default of 3600 seconds (1 hour) for empty or zero-length durations.

#### Scenario: Empty string

- GIVEN the input ""
- WHEN the parser runs
- THEN it returns 3600
