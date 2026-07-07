/**
 * Ticket invariant helpers — pure TS mirror of `bot/services/ticket_invariants.py`.
 *
 * These helpers enforce the shared ticket invariant contract used identically by
 * the bot (Python) and the dashboard (TS). They are PURE: no Supabase, no
 * Discord, no React, no side effects. Each validator either returns `void` on
 * success or throws an `Error` with a human-readable reason.
 *
 * This module is CLIENT-SAFE (no `node:` imports) so client components — e.g.
 * {@link NotesPanel} reading `NOTE_CAP` to disable the add form — can import it
 * without pulling Node-only APIs into the browser bundle. The normalized-dedup
 * hash (`computeNoteHash` / `isDuplicateNote`) lives in the server-only module
 * {@link TicketInvariantsServer} (`ticket-invariants.server.ts`) because it
 * uses `node:crypto`.
 *
 * Contract scenarios TI-001..TI-038 are mirrored 1:1 in
 * `dashboard/__tests__/contract/ticket-invariants.test.ts`. Mirroring the
 * Python helper names + the normalized-dedup hash formula (decision #9,
 * engram #669) keeps the two suites drift-catchable in CI.
 *
 * The Note dedup hash = SHA256 of `trim(content).lower().collapse_whitespace()`
 * — exactly `sha256(" ".join(content.strip().lower().split()))` in Python.
 */

/** Per-ticket note cap enforced by the dashboard and the bot service (B5). */
export const NOTE_CAP = 50;

/** Dedup window (seconds) for same-author duplicate notes. */
export const NOTE_DEDUP_WINDOW_SECONDS = 2;

// ---------------------------------------------------------------------------
// Status state machine
// ---------------------------------------------------------------------------

/** Validate that a claim may proceed (open + unclaimed). Throws on violation. */
export function checkCanClaim(ticketStatus: string, claimedBy: string | null): void {
  if (ticketStatus !== "open") {
    throw new Error(`Cannot claim a ticket with status '${ticketStatus}' (must be open)`);
  }
  if (claimedBy !== null) {
    throw new Error("Cannot claim a ticket that is already claimed (use transfer)");
  }
}

/** Validate that a close may proceed (open or claimed). Throws on closed. */
export function checkCanClose(ticketStatus: string): void {
  if (ticketStatus === "closed") {
    throw new Error("Cannot close a ticket that is already closed");
  }
  if (ticketStatus !== "open" && ticketStatus !== "claimed") {
    throw new Error(`Cannot close a ticket with status '${ticketStatus}'`);
  }
}

/** Validate that a reopen may proceed (closed only — status guard). Throws otherwise. */
export function checkCanReopen(ticketStatus: string): void {
  if (ticketStatus !== "closed") {
    throw new Error(`Cannot reopen a ticket with status '${ticketStatus}' (must be closed)`);
  }
}

/**
 * Validate that a transfer may proceed. Transfer reassigns `claimedBy` AND
 * sets `status='claimed'` (implicit re-claim). Rules:
 * - A closed ticket cannot be transferred (reopen it first).
 * - The target MUST be specified.
 * - The target MUST differ from the current claimant (no-op transfer denied).
 */
export function checkCanTransfer(
  ticketStatus: string,
  currentClaimedBy: string | null,
  targetId: string | null
): void {
  if (ticketStatus === "closed") {
    throw new Error("Cannot transfer a closed ticket (reopen it first)");
  }
  if (targetId === null) {
    throw new Error("Cannot transfer a ticket without a target staff member");
  }
  if (currentClaimedBy !== null && targetId === currentClaimedBy) {
    throw new Error(
      "Cannot transfer a ticket to the same staff member who already claimed it"
    );
  }
}

// ---------------------------------------------------------------------------
// Notes — cap + ownership
// ---------------------------------------------------------------------------

/**
 * Validate that a note may be added given the current `existingCount`.
 * Throws when the ticket has reached or exceeded `cap`.
 */
export function checkCanAddNote(existingCount: number, cap: number = NOTE_CAP): void {
  if (existingCount >= cap) {
    throw new Error(
      `Cannot add a note: ticket has reached the ${cap}-note cap (${existingCount} notes)`
    );
  }
}

/**
 * Validate that `actorId` may delete a note authored by `noteAuthorId`.
 * Only the note's author may delete it (author-only rule). Throws otherwise.
 */
export function checkCanDeleteNote(noteAuthorId: string, actorId: string): void {
  if (actorId !== noteAuthorId) {
    throw new Error("Only the note's author may delete a note");
  }
}

// ---------------------------------------------------------------------------
// Subticket parentId FK invariants (depth max 2, app-level FK)
// ---------------------------------------------------------------------------

/** A camelCase parent ticket row (the subset read by the invariant). */
export interface ParentTicketRow {
  id: string;
  guildId: string;
  parentId: string | null;
}

/**
 * Validate that `parent` is a legal subticket parent for the current ticket.
 *
 * Rules (depth max 2, app-level FK — no DB FK):
 * - The parent row MUST exist (not `null`).
 * - The parent MUST NOT be the child itself (no self-reference).
 * - The parent MUST NOT already have a `parentId` (depth cap = 2).
 * - The parent MUST belong to the same guild as the child.
 */
export function checkSubticketParent(
  parent: ParentTicketRow | null,
  parentGuildId: string,
  currentGuildId: string,
  currentId?: string
): void {
  if (parent === null) {
    throw new Error("Subticket parent not found");
  }
  if (currentId !== undefined && parent.id === currentId) {
    throw new Error("A ticket cannot be its own parent (self-reference)");
  }
  if (parent.parentId !== null) {
    throw new Error("Subticket parent is itself a subticket (depth limit is 2)");
  }
  if (parentGuildId !== currentGuildId) {
    throw new Error("Subticket parent must belong to the same guild as the child");
  }
}