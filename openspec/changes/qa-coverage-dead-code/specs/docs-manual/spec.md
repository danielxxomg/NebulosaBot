# Delta for Docs Manual

## ADDED Requirements

### Requirement: Dynamic hybrid command discovery test

The system MUST have a test that discovers all `@commands.hybrid_command` decorated functions at runtime and asserts each appears in `docs/MANUAL.md` with a description.

#### Scenario: all hybrid commands appear in manual

- GIVEN all cog modules imported and `@hybrid_command` functions discovered
- WHEN each command name is searched in `docs/MANUAL.md`
- THEN every discovered command name appears at least once

#### Scenario: each command has a description

- GIVEN a hybrid command name found in MANUAL.md
- WHEN the surrounding text is inspected
- THEN a non-empty description line follows the command name

#### Scenario: discovery is resilient to cog load order

- GIVEN cog modules imported in arbitrary order
- WHEN command discovery runs
- THEN the discovered command set is identical regardless of import order
