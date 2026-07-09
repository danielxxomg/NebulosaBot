-- Migration 014: Add JSONB field_definitions to ticket_category and custom_fields to ticket.
-- Idempotent: uses IF NOT EXISTS so re-applying is safe.
-- field_definitions stores per-category intake field schemas (0-3 entries).
-- custom_fields stores submitted values on each ticket row.

ALTER TABLE ticket_category
    ADD COLUMN IF NOT EXISTS "fieldDefinitions" jsonb DEFAULT '[]'::jsonb;

ALTER TABLE ticket
    ADD COLUMN IF NOT EXISTS "customFields" jsonb DEFAULT '{}'::jsonb;

-- Seed the Reportes category with player_nick (required) + evidence_url (optional).
-- Match by lower(trim(name)) = 'reportes' to handle whitespace/case variance.
UPDATE ticket_category
SET "fieldDefinitions" = '[
  {"key": "player_nick", "label": "Player Nickname", "style": "short", "required": true, "placeholder": "The player''s in-game name"},
  {"key": "evidence_url", "label": "Evidence URL", "style": "short", "required": false}
]'::jsonb
WHERE lower(trim(name)) = 'reportes'
  AND ("fieldDefinitions" IS NULL OR "fieldDefinitions" = '[]'::jsonb);
