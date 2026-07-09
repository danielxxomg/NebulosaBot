# Delta for Ticket Category Model

## MODIFIED Requirements

### Requirement: Dataclass fields

The system MUST define a TicketCategory dataclass with fields: `id` (UUID), `guildId` (string), `name` (string), `description` (nullable string), `position` (integer), `createdAt` (datetime), `fieldDefinitions` (list[dict], default `[]`). `from_db_row` SHALL map `row["fieldDefinitions"]` to `field_definitions`. `to_db_dict` SHALL include `"fieldDefinitions": self.field_definitions`.

(Previously: no `fieldDefinitions` field on the dataclass)

#### Scenario: Build from row

- GIVEN a Supabase row with camelCase keys
- WHEN `from_db_row` is called
- THEN a TicketCategory instance is returned with correct field values

#### Scenario: Build from row with field_definitions

- GIVEN a Supabase row with `fieldDefinitions = [{"key": "player_nick", "label": "Player Nickname", "style": "short", "required": true}]`
- WHEN `from_db_row` is called
- THEN `ticket_category.field_definitions` contains one entry with key "player_nick"

#### Scenario: Build from row without field_definitions

- GIVEN a Supabase row with `fieldDefinitions = null` or missing
- WHEN `from_db_row` is called
- THEN `ticket_category.field_definitions` defaults to `[]`

#### Scenario: Serialize with field_definitions

- GIVEN a TicketCategory with `field_definitions = [{"key": "player_nick", "label": "Player Nickname", "style": "short", "required": true}]`
- WHEN `to_db_dict()` is called
- THEN the dict includes `"fieldDefinitions": [{"key": "player_nick", ...}]`

#### Scenario: Serialize with empty field_definitions

- GIVEN a TicketCategory with `field_definitions = []`
- WHEN `to_db_dict()` is called
- THEN the dict includes `"fieldDefinitions": []`
