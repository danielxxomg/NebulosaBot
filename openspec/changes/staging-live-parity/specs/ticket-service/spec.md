# Delta for Ticket Service

## ADDED Requirements

### Requirement: Optional bounded S4 error-path polish

If the optional S4 polish slice is included, the ticket repair and panel test suites MUST raise line coverage for `ticket_repair_service.py` and `ticket_panel.py` from the 73% baseline to at least 80% per file. Tests MUST target only the identified error, fallback, no-op, and Discord-exception branches, preserve existing user-visible behavior, and MUST NOT use fake coverage as proof of live Supabase parity.

#### Scenario: Target coverage reaches the bounded goal

- GIVEN both changed files begin at the 73% baseline
- WHEN the focused S4 polish suite runs
- THEN each file reports at least 80% line coverage

#### Scenario: Error paths remain reviewable

- GIVEN a repair or panel operation encounters a configured failure, missing resource, no-op, or Discord exception
- WHEN the focused tests exercise that branch
- THEN the documented error handling is asserted and no uncaught traceback reaches the user

#### Scenario: Polish stays out of scope

- GIVEN unrelated Sentinel or pre-existing coverage debt exists
- WHEN S4 polish coverage is measured
- THEN it is excluded from the target and no unrelated behavior is changed
