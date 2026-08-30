# Delta for docs-manual

## MODIFIED Requirements

### Requirement: User manual structure

`docs/MANUAL.md` MUST exist in Spanish with exactly 7 sections: Inicio Rápido, Comandos de Usuario, Comandos de Moderación, Comandos de Administración, Configuración, Sistema de Tickets, Comandos Slash (previously Comandos Híbridos). Each section MUST have a one-line purpose description. The default language reference MUST state `es` (Spanish), not `en`. No hybrid/prefix terminology outside historical notes; help and manual MUST show slash syntax only (`/command`) per `bot-core` (`get_prefix -> []`).

(Previously: 7 sections ended with Comandos Híbridos; manual incorrectly claimed default language was `en`)

#### Scenario: Manual file exists with correct structure

- GIVEN the repository root
- WHEN `docs/MANUAL.md` is read
- THEN the file exists, is non-empty, and contains exactly 7 `##` section headings in the specified order with the last being Comandos Slash

#### Scenario: Each section has a purpose line

- GIVEN each of the 7 sections in the manual
- WHEN the section content is read
- THEN the first non-heading line is a brief purpose description

#### Scenario: Default language is Spanish

- GIVEN the manual's language configuration section
- WHEN the default language is referenced
- THEN it states `es` (Spanish), not `en` (English)

### Requirement: Per-command syntax and permissions

Each command entry MUST include: command name, description, Discord slash syntax in code block (`/command`), permission level (everyone/mod/admin via `can_check`/matrix or `is_admin`), parameters in table format with name/type/required/description, and at least one practical example. Prefix syntax MUST NOT be documented as invocable; `prefix` is data-only (`guild-config`) and the `,` timer is documented only under Sistema de Tickets via `close-confirmation`.

(Previously: slash and prefix syntax both documented for hybrid commands)

#### Scenario: Command entry has all required fields

- GIVEN any command documented in the manual
- WHEN the command entry is inspected
- THEN it contains: name, description, `/command` syntax code block, permission badge, parameter table, and at least one example via `t()` keys where applicable

#### Scenario: Slash syntax only documented

- GIVEN a slash command
- WHEN the syntax section is read
- THEN only `/command` syntax is shown and no `!command`/`nb!command` prefix example is shown as invocable

### Requirement: Hybrid commands section

A dedicated Slash Commands section (previously Hybrid commands section) MUST list all 17 slash commands with their slash syntax (`/command`) and explain that all commands are invoked via Discord slash commands only (no prefix path; `get_prefix -> []`). It MUST explain that errors are shown as ephemeral replies via `t()` and that the `,` close-confirmation timer (in `TicketsCog.on_message`) is not a command prefix and remains specified by `close-confirmation`.

(Previously: listed all 17 hybrid commands with slash and prefix syntax and explained slash vs prefix differences)

#### Scenario: All slash commands listed

- GIVEN the slash commands section
- WHEN the section is read
- THEN all 17 slash commands are listed with `/command` syntax only (no `!command`)

#### Scenario: Slash-only behavior explained

- GIVEN the slash commands section introduction
- WHEN the introduction is read
- THEN it explains that commands are slash-only and ephemeral error handling, with no prefix invocation path

#### Scenario: Comma timer correctly scoped

- GIVEN the manual's ticket close description
- WHEN the `,` timer is mentioned
- THEN it is described as the `TicketsCog.on_message` timer under `close-confirmation`, not as a command prefix
