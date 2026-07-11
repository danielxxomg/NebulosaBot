# Delta for core-commands

## MODIFIED Requirements

### Requirement: Help command

The system MUST provide a `help` command that returns a custom embed organized by module with pagination. The paginator MUST localize Previous/Next/Stop button labels via `t()` using the invoking guild's language.

(Previously: paginator buttons were hardcoded English "◀ Previous", "Next ▶", "⏹ Stop")

#### Scenario: Help without module

- GIVEN a user invokes `help`
- WHEN no module is specified
- THEN the bot lists available modules

#### Scenario: Help with module

- GIVEN a user invokes `help Sentinel`
- WHEN the module exists
- THEN the bot returns an embed with Sentinel commands and pagination if needed

#### Scenario: Paginator shows Spanish buttons in Spanish guild

- GIVEN a guild with language `es`
- WHEN a user invokes `help` with multiple pages
- THEN the paginator buttons show Spanish labels (e.g., "Anterior", "Siguiente", "Detener")

#### Scenario: Paginator shows English buttons in English guild

- GIVEN a guild with language `en`
- WHEN a user invokes `help` with multiple pages
- THEN the paginator buttons show English labels (e.g., "Previous", "Next", "Stop")
