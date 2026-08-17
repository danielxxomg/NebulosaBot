-- Migration 017: Widen ticket_audit.outcome to include 'repaired'
-- Idempotent: drops existing check and recreates with repaired outcome.
-- Required for ticket-integrity-recovery spec: automatic/manual repair must persist 'repaired', not 'success'.
-- Live DB currently has CHECK (outcome IN ('success','denied','error')); this widens to include 'repaired' while preserving existing values.
-- No data migration, no down-migration: retains fail-closed behavior (G.2 stays gate_unresolved until fresh evidence).

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ticket_audit_outcome_check'
        AND conrelid = 'ticket_audit'::regclass
    ) THEN
        ALTER TABLE ticket_audit DROP CONSTRAINT ticket_audit_outcome_check;
    END IF;
END $$;

-- Recreate constraint with widened vocabulary. IF the constraint still exists under an auto-generated name, drop any check on outcome.
DO $$
DECLARE
    _conname text;
BEGIN
    SELECT conname INTO _conname
    FROM pg_constraint
    WHERE conrelid = 'ticket_audit'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) ILIKE '%outcome%IN%'
    LIMIT 1;
    IF _conname IS NOT NULL THEN
        EXECUTE format('ALTER TABLE ticket_audit DROP CONSTRAINT %I', _conname);
    END IF;
END $$;

ALTER TABLE ticket_audit
    ADD CONSTRAINT ticket_audit_outcome_check
    CHECK (outcome IN ('success', 'denied', 'error', 'repaired'));
