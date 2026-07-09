# Delta for Ticket Model

## MODIFIED Requirements

### Requirement: Ticket dataclass parent_id field

The `Ticket` dataclass MUST include `parent_id: str | None = None`, `subject: str | None = None`, `description: str | None = None`, and `custom_fields: dict | None = None`. `from_db_row` SHALL map `row["parentId"]`, `row["subject"]`, `row["description"]`, and `row["customFields"]`. `to_db_dict` SHALL include `"parentId": self.parent_id`, `"subject": self.subject`, `"description": self.description`, and `"customFields": self.custom_fields`.

(Previously: no `custom_fields` field on the dataclass)

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

#### Scenario: Deserialize ticket with subject and description

- GIVEN a DB row with `subject = "Login broken"` and `description = "Cannot access"`
- WHEN `Ticket.from_db_row(row)` is called
- THEN `ticket.subject == "Login broken"` and `ticket.description == "Cannot access"`

#### Scenario: Deserialize ticket without subject and description

- GIVEN a DB row with `subject = null` and `description = null`
- WHEN `Ticket.from_db_row(row)` is called
- THEN `ticket.subject is None` and `ticket.description is None`

#### Scenario: Serialize ticket with subject and description

- GIVEN a Ticket with `subject = "Bug"` and `description = "Details"`
- WHEN `ticket.to_db_dict()` is called
- THEN the dict includes `"subject": "Bug"` and `"description": "Details"`

#### Scenario: Deserialize ticket with custom_fields

- GIVEN a DB row with `customFields = {"player_nick": "DarkSlayer42", "evidence_url": "https://imgur.com/..."}`
- WHEN `Ticket.from_db_row(row)` is called
- THEN `ticket.custom_fields == {"player_nick": "DarkSlayer42", "evidence_url": "https://imgur.com/..."}`

#### Scenario: Deserialize ticket without custom_fields

- GIVEN a DB row with `customFields = null` or missing
- WHEN `Ticket.from_db_row(row)` is called
- THEN `ticket.custom_fields is None`

#### Scenario: Serialize ticket with custom_fields

- GIVEN a Ticket with `custom_fields = {"player_nick": "DarkSlayer42"}`
- WHEN `ticket.to_db_dict()` is called
- THEN the dict includes `"customFields": {"player_nick": "DarkSlayer42"}`

#### Scenario: Serialize ticket without custom_fields

- GIVEN a Ticket with `custom_fields = None`
- WHEN `ticket.to_db_dict()` is called
- THEN the dict includes `"customFields": None`
