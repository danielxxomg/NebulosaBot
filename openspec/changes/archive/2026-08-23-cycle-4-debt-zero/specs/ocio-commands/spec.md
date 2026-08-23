# Delta for Ocio Commands

## MODIFIED Requirements

### Requirement: 8ball command

The system MUST provide a `/8ball` hybrid command that returns one of 20 localized responses (Spanish and English, via `t()`) to a yes/no question. The response MUST be chosen uniformly at random from the 20-key set. The command's embed MUST use the localized `ocio.8ball.embed_title` key — a raw key MUST never be rendered to users. The command MUST be ephemeral and MUST NOT write to the database.

(Previously: only the 20 response keys existed; the embed title was not localized.)

#### Scenario: 8ball returns a localized response

- GIVEN a member invokes `/8ball` with a question in a Spanish guild
- WHEN the command executes
- THEN the bot replies ephemerally with one of the 20 Spanish `ocio.8ball.*` responses

#### Scenario: 8ball title is localized

- GIVEN members invoke `/8ball` in Spanish and English guilds
- WHEN the embed is rendered
- THEN the title comes from `ocio.8ball.embed_title` in each guild's language (no raw key shown)

#### Scenario: 8ball is i18n-isolated

- GIVEN the 20-key `ocio.8ball.*` set exists in `es.json` and `en.json`
- WHEN an English-guild member invokes `/8ball`
- THEN the reply uses the English set and Spanish and English outputs are independently testable

#### Scenario: 8ball writes no DB row

- GIVEN a member invokes `/8ball`
- WHEN the command executes
- THEN no row is inserted, updated, or deleted in any table
