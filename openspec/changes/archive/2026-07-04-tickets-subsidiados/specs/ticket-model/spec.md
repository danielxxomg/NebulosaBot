# Ticket Model Specification

## Purpose

Define the `Ticket` and `TicketNote` dataclasses that mirror their respective database tables.

## Requirements

### Requirement: Ticket dataclass parent_id field

The `Ticket` dataclass MUST include `parent_id: str | None = None`. The `from_db_row` classmethod SHALL map `row["parentId"]` to `parent_id`. The `to_db_dict` method SHALL include `"parentId": self.parent_id`.

#### Scenario: Deserialize ticket with parentId

- GIVEN a DB row with `parentId = "abc-123"`
- WHEN `Ticket.from_db_row(row)` is called
- THEN `ticket.parent_id == "abc-123"`

#### Scenario: Deserialize ticket without parentId

- GIVEN a DB row with `parentId = null`
- WHEN `Ticket.from_db_row(row)` is called
- THEN `ticket.parent_id is None`

#### Scenario: Serialize ticket with parentId

- GIVEN a Ticket with `parent_id = "abc-123"`
- WHEN `ticket.to_db_dict()` is called
- THEN the dict includes `"parentId": "abc-123"`

#### Scenario: Serialize ticket without parentId

- GIVEN a Ticket with `parent_id = None`
- WHEN `ticket.to_db_dict()` is called
- THEN the dict includes `"parentId": None`

### Requirement: TicketNote dataclass

The system MUST provide a `TicketNote` dataclass with fields: `id` (str UUID), `ticket_id` (str), `author_id` (str), `content` (str), `created_at` (datetime). A `from_db_row` classmethod SHALL map camelCase DB keys to snake_case attributes. A `to_db_dict` method SHALL convert back to camelCase.

#### Scenario: Deserialize note

- GIVEN a DB row `{"id": "n1", "ticketId": "t1", "authorId": "s1", "content": "text", "createdAt": "2025-01-01T00:00:00Z"}`
- WHEN `TicketNote.from_db_row(row)` is called
- THEN `note.id == "n1"`, `note.ticket_id == "t1"`, `note.author_id == "s1"`, `note.content == "text"`

#### Scenario: Serialize note

- GIVEN a TicketNote instance
- WHEN `note.to_db_dict()` is called
- THEN the dict uses camelCase keys (`ticketId`, `authorId`, `createdAt`)
