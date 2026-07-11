# Delta for docs-manual

## MODIFIED Requirements

### Requirement: User manual structure

`docs/MANUAL.md` MUST exist in Spanish with exactly 7 sections: Inicio Rápido, Comandos de Usuario, Comandos de Moderación, Comandos de Administración, Configuración, Sistema de Tickets, Comandos Híbridos. Each section MUST have a one-line purpose description. The default language reference MUST state `es` (Spanish), not `en` (English).

(Previously: manual incorrectly claimed default language was `en`)

#### Scenario: Manual file exists with correct structure

- GIVEN the repository root
- WHEN `docs/MANUAL.md` is read
- THEN the file exists, is non-empty, and contains exactly 7 `##` section headings in the specified order

#### Scenario: Each section has a purpose line

- GIVEN each of the 7 sections in the manual
- WHEN the section content is read
- THEN the first non-heading line is a brief purpose description

#### Scenario: Default language is Spanish

- GIVEN the manual's language configuration section
- WHEN the default language is referenced
- THEN it states `es` (Spanish), not `en` (English)

#### Scenario: Language parameter default documented correctly

- GIVEN the manual's configuration section
- WHEN the `language` parameter is documented
- THEN the default value is `es` with a note that responses are in Spanish by default
