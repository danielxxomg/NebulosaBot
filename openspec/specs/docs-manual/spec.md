# Docs Manual Specification

## Purpose

Comprehensive Spanish user manual covering all bot functionality with per-command syntax, permission tables, and atomic operation documentation.

## Requirements

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

### Requirement: Per-command syntax and permissions

Each command entry MUST include: command name, description, Discord syntax in code block, permission level (everyone/mod/admin), parameters in table format with name/type/required/description, and at least one practical example.

#### Scenario: Command entry has all required fields

- GIVEN any command documented in the manual
- WHEN the command entry is inspected
- THEN it contains: name, description, syntax code block, permission badge, parameter table, and at least one example

#### Scenario: Slash and prefix syntax both documented

- GIVEN a hybrid command
- WHEN the syntax section is read
- THEN both `/command` and `!command` syntax variants are shown

### Requirement: Moderation commands atomic operations

Moderation commands (warn, mute, kick, ban) MUST document each as an atomic operation with: what it does, permission required, DM notification behavior, and audit log entry.

#### Scenario: Warn command is fully documented

- GIVEN the moderation section
- WHEN the warn command entry is read
- THEN it documents: infraction recording, DM notification, permission requirement, and audit log behavior

#### Scenario: Kick/ban confirmation dialogs documented

- GIVEN the moderation section
- WHEN kick or ban entries are read
- THEN they document the ephemeral Confirm/Cancel confirmation dialog

### Requirement: Ticket system section completeness

The ticket system section MUST document: creation flow, claiming, closing (with confirmation dialog), channel naming format, and all subcommands.

#### Scenario: Ticket creation flow documented

- GIVEN the ticket system section
- WHEN the creation flow is read
- THEN it describes the category selector, intake modal, and channel creation

#### Scenario: Close confirmation documented

- GIVEN the ticket system section
- WHEN the close operation is read
- THEN it describes the ephemeral Confirm/Cancel dialog and that dismiss = cancel

### Requirement: Hybrid commands section

A dedicated hybrid commands section MUST list all 17 hybrid commands with their slash and prefix syntax, and explain the difference between slash and prefix invocations.

#### Scenario: All hybrid commands listed

- GIVEN the hybrid commands section
- WHEN the section is read
- THEN all 17 hybrid commands are listed with both `/command` and `!command` syntax

#### Scenario: Slash vs prefix behavior explained

- GIVEN the hybrid commands section
- WHEN the introduction is read
- THEN it explains that slash commands show errors as ephemeral replies while prefix commands send to channel
