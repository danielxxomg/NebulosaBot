"use server";

import { createServerSupabaseClient, createServiceClient } from "@/lib/supabase";
import { fetchUserGuilds, hasAdministratorPerm } from "@/lib/discord";
import type { Ticket, TicketNote, TicketAudit } from "@/lib/types";
import {
  checkCanAddNote,
  checkCanDeleteNote,
  NOTE_CAP,
  NOTE_DEDUP_WINDOW_SECONDS,
} from "@/lib/ticket-invariants";
import {
  computeNoteHash,
  isDuplicateNote,
} from "@/lib/ticket-invariants.server";

/** Reopen guidance returned by {@link getReopenGuidance}. */
export interface ReopenGuidance {
  /** The ticket number, zero-padded to 4 digits (#0003). */
  ticketNumber: number;
  /** The literal command to run in Discord: `/reopen ticket:#0003`. */
  command: string;
}

/**
 * Result of fetching a guild's tickets.
 *
 * - Success: `{ data: Ticket[], error: null }`
 * - Auth or database failure: `{ data: null, error: string }`
 */
export type TicketListResult =
  | { data: Ticket[]; error: null }
  | { data: null; error: string };

/**
 * Result of a ticket mutation (transfer / add note / delete note).
 *
 * Mutations do not return the affected row; success is `{ data: null, error: null }`.
 * Auth, not-found, or database failures are `{ data: null, error: string }`.
 */
export type TicketMutationResult =
  | { data: null; error: null }
  | { data: null; error: string };

/**
 * Result of fetching a ticket's internal notes.
 *
 * - Success: `{ data: TicketNote[], error: null }`
 * - Auth or database failure: `{ data: null, error: string }`
 */
export type TicketNoteListResult =
  | { data: TicketNote[]; error: null }
  | { data: null, error: string };

/**
 * Result of fetching reopen guidance for a closed ticket.
 *
 * - Success: `{ data: ReopenGuidance, error: null }`
 * - Auth, not-found, or category-not-configured: `{ data: null, error: string }`
 */
export type ReopenGuidanceResult =
  | { data: ReopenGuidance; error: null }
  | { data: null; error: string };

/**
 * Result of fetching paginated audit rows.
 *
 * - Success: `{ data: TicketAudit[], error: null }`
 * - Auth or database failure: `{ data: null, error: string }`
 */
export type TicketAuditListResult =
  | { data: TicketAudit[]; error: null }
  | { data: null; error: string };

/** Hard cap on rows returned per request. Pagination is out of scope for v1. */
const TICKET_PAGE_LIMIT = 50;
/** Page size for the audit panel. */
const AUDIT_PAGE_SIZE = 20;

/**
 * Re-verify the current user has admin access to the target guild.
 *
 * Called inside every Server Action as defense-in-depth beyond the
 * layout-level permission guard. Service-role reads must not rely only on
 * the route layout.
 *
 * Returns `null` when auth passes, or an `{ success: false, error }`
 * result describing why it failed.
 */
async function verifyGuildAdmin(
  guildId: string
): Promise<{ success: false; error: string } | null> {
  const supabase = await createServerSupabaseClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) {
    return { success: false, error: "Not authenticated." };
  }

  const providerToken = session.provider_token;
  if (!providerToken) {
    return {
      success: false,
      error: "Discord token not available. Please re-login.",
    };
  }

  // Verify guild is active.
  const serviceClient = await createServiceClient();
  const { data: guild } = await serviceClient
    .from("guild")
    .select("active")
    .eq("id", guildId)
    .single();

  if (!guild || !guild.active) {
    return { success: false, error: "Guild not found or inactive." };
  }

  // Verify admin permission.
  const userGuilds = await fetchUserGuilds(providerToken);
  const target = userGuilds.find((g) => g.id === guildId);

  if (!target || !hasAdministratorPerm(target.permissions)) {
    return {
      success: false,
      error: "You must be a server administrator to view tickets.",
    };
  }

  return null; // null = auth passed
}

/**
 * Resolve the current session user's Discord user id.
 *
 * Reads from the Supabase session's Discord identity
 * (`session.user.identities[0].id`), falling back to `session.user.id`. Used
 * as the `authorId` for note inserts and the `actorId` for note-delete
 * ownership checks.
 */
async function resolveSessionUserId(): Promise<string> {
  const supabase = await createServerSupabaseClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  return session?.user?.identities?.[0]?.id ?? session?.user?.id ?? "unknown";
}

/**
 * Server-exposed wrapper around {@link resolveSessionUserId}.
 *
 * Used by client components (e.g. {@link NotesPanel}) to know which notes are
 * their own so the delete button only renders for the note's author. The
 * server action {@link deleteTicketNote} STILL enforces ownership — this is a
 * UX affordance, not a security boundary.
 *
 * Returns `"unknown"` when no session is available (the page layout guard
 * ensures a session exists before this is reachable in practice).
 */
export async function getCurrentUserId(): Promise<string> {
  return resolveSessionUserId();
}

/**
 * Fetch up to {@link TICKET_PAGE_LIMIT} tickets for a guild, newest first.
 *
 * Auth-gated by {@link verifyGuildAdmin}: unauthenticated, tokenless,
 * inactive-guild, or non-admin callers receive an error and no data.
 * Guild isolation is enforced via `.eq("guildId", guildId)` so tickets
 * from other guilds can never leak into the result set.
 */
export async function getTicketsForGuild(
  guildId: string
): Promise<TicketListResult> {
  const authError = await verifyGuildAdmin(guildId);
  if (authError) {
    return { data: null, error: authError.error };
  }

  const serviceClient = await createServiceClient();
  const { data: tickets, error } = await serviceClient
    .from("ticket")
    .select("*")
    .eq("guildId", guildId)
    .order("createdAt", { ascending: false })
    .limit(TICKET_PAGE_LIMIT);

  if (error) {
    return { data: null, error: `Database error: ${error.message}` };
  }

  return { data: tickets ?? [], error: null };
}

// ---------------------------------------------------------------------------
// Ticket-scoped mutation / note actions
// ---------------------------------------------------------------------------

/**
 * Resolve the guild a ticket belongs to, then re-verify the caller is an
 * administrator of THAT guild.
 *
 * All ticket-scoped actions below take a `ticketId` (or `noteId`) rather than
 * a `guildId`, so they must look the ticket up first to know which guild to
 * authorize against. This is the single chokepoint that enforces guild
 * isolation for every ticket-scoped mutation/read.
 *
 * Returns `{ guildId }` on success, or `{ error }` describing a database,
 * not-found, or auth failure.
 */
async function resolveTicketGuild(
  ticketId: string
): Promise<{ guildId: string } | { error: string }> {
  const serviceClient = await createServiceClient();
  const { data, error } = await serviceClient
    .from("ticket")
    .select("guildId")
    .eq("id", ticketId)
    .single();

  if (error) {
    return { error: `Database error: ${error.message}` };
  }
  if (!data) {
    return { error: "Ticket not found." };
  }

  const guildId = (data as { guildId: string }).guildId;
  const authError = await verifyGuildAdmin(guildId);
  if (authError) {
    return { error: authError.error };
  }

  return { guildId };
}

/**
 * Return "Reopen in Discord" guidance for a closed ticket (decision #2a /
 * engram #669).
 *
 * Loads the ticket + guild config, rejects missing `ticketCategoryId` with
 * "Ticket category is not configured", and only then returns the ticket
 * number (zero-padded) plus the literal command `/reopen ticket:#<number>`.
 * CRITICAL: this action MUST NOT update the `ticket` table — a DB-only status
 * flip would create a zombie ticket with no Discord channel (the original
 * channel is deleted on close). The bot's `/reopen` creates the new channel.
 */
export async function getReopenGuidance(
  ticketId: string
): Promise<ReopenGuidanceResult> {
  const resolved = await resolveTicketGuild(ticketId);
  if ("error" in resolved) {
    return { data: null, error: resolved.error };
  }

  const serviceClient = await createServiceClient();

  // Load the ticket (need the ticketNumber) and the guild config (need the
  // ticketCategoryId gate). Both are read-only; no mutation happens here.
  const { data: ticket, error: ticketError } = await serviceClient
    .from("ticket")
    .select("ticketNumber")
    .eq("id", ticketId)
    .single();

  if (ticketError) {
    return { data: null, error: `Database error: ${ticketError.message}` };
  }
  if (!ticket) {
    return { data: null, error: "Ticket not found." };
  }

  const { data: guild, error: guildError } = await serviceClient
    .from("guild")
    .select("ticketCategoryId")
    .eq("id", (resolved as { guildId: string }).guildId)
    .single();

  if (guildError) {
    return { data: null, error: `Database error: ${guildError.message}` };
  }
  if (!guild) {
    return { data: null, error: "Guild not found." };
  }

  // Category gate: the bot /reopen would fail without a configured category,
  // so the dashboard MUST NOT show the command when the category is missing
  // or blank (decision table / dashboard-ticket-view spec).
  const ticketCategoryId = (guild as { ticketCategoryId: string | null })
    .ticketCategoryId;
  if (!ticketCategoryId || ticketCategoryId.trim() === "") {
    return { data: null, error: "Ticket category is not configured." };
  }

  const ticketNumber = (ticket as { ticketNumber: number }).ticketNumber;
  const padded = String(ticketNumber).padStart(4, "0");
  return {
    data: { ticketNumber, command: `/reopen ticket:#${padded}` },
    error: null,
  };
}

/**
 * Transfer a ticket's claim to a different staff member (decision #3 /
 * engram #669).
 *
 * Updates BOTH `claimedBy` AND `status` (to `"claimed"`). Transfer is an
 * implicit re-claim — transferring an open ticket claims it for the new
 * assignee; reassigning a claimed ticket keeps it claimed under the new
 * claimant. Auth-gated by {@link resolveTicketGuild}: only an administrator of
 * the ticket's guild may transfer it.
 */
export async function transferTicket(
  ticketId: string,
  newClaimedBy: string
): Promise<TicketMutationResult> {
  const resolved = await resolveTicketGuild(ticketId);
  if ("error" in resolved) {
    return { data: null, error: resolved.error };
  }

  const serviceClient = await createServiceClient();
  const { error } = await serviceClient
    .from("ticket")
    .update({ claimedBy: newClaimedBy, status: "claimed" })
    .eq("id", ticketId);

  if (error) {
    return { data: null, error: `Database error: ${error.message}` };
  }

  return { data: null, error: null };
}

/**
 * Fetch the internal notes attached to a ticket, newest first.
 *
 * Returns up to {@link TICKET_PAGE_LIMIT} notes. Auth-gated by
 * {@link resolveTicketGuild}: notes are only visible to an administrator of
 * the ticket's guild (guild isolation — a note on guild A's ticket is never
 * exposed to an admin of guild B).
 */
export async function getTicketNotes(
  ticketId: string
): Promise<TicketNoteListResult> {
  const resolved = await resolveTicketGuild(ticketId);
  if ("error" in resolved) {
    return { data: null, error: resolved.error };
  }

  const serviceClient = await createServiceClient();
  const { data: notes, error } = await serviceClient
    .from("ticket_note")
    .select("*")
    .eq("ticketId", ticketId)
    .order("createdAt", { ascending: false })
    .limit(TICKET_PAGE_LIMIT);

  if (error) {
    return { data: null, error: `Database error: ${error.message}` };
  }

  return { data: (notes as TicketNote[]) ?? [], error: null };
}

/**
 * Add an internal note to a ticket.
 *
 * Enforces:
 * - The 50-note cap (decision #4 / TI-031): the note count is read before
 *   insert and the action rejects with a cap-reached error when at the limit.
 * - Note dedup (decision #9 / TI-016): the incoming content is normalized
 *   (`trim().toLowerCase().collapseWhitespace()` → SHA256) and compared
 *   against the same author's notes within a 2-second window. A normalized
 *   duplicate is rejected without insert.
 *
 * Auth-gated by {@link resolveTicketGuild}: only an administrator of the
 * ticket's guild may add notes.
 */
export async function addTicketNote(
  ticketId: string,
  content: string
): Promise<TicketMutationResult> {
  const resolved = await resolveTicketGuild(ticketId);
  if ("error" in resolved) {
    return { data: null, error: resolved.error };
  }

  const authorId = await resolveSessionUserId();

  const serviceClient = await createServiceClient();

  // Read existing notes newest-first, capped at NOTE_CAP + 1 so we can compute
  // the cap check AND the dedup hash set in a single query (the dedup only
  // considers author-scoped notes within a 2s window, both filtered in-app).
  const { data: existing, error: readError } = await serviceClient
    .from("ticket_note")
    .select("*")
    .eq("ticketId", ticketId)
    .order("createdAt", { ascending: false })
    .limit(NOTE_CAP + 1);

  if (readError) {
    return { data: null, error: `Database error: ${readError.message}` };
  }

  const existingNotes = (existing as TicketNote[]) ?? [];

  // Cap enforcement — reject before insert.
  try {
    checkCanAddNote(existingNotes.length, NOTE_CAP);
  } catch (err) {
    return { data: null, error: (err as Error).message };
  }

  // Dedup — same author, within the 2s window, normalized content match.
  const now = Date.now();
  const windowMs = NOTE_DEDUP_WINDOW_SECONDS * 1000;
  const incomingHash = computeNoteHash(content);
  const recentSameAuthorHashes = existingNotes
    .filter(
      (n) =>
        n.authorId === authorId &&
        now - new Date(n.createdAt).getTime() <= windowMs
    )
    .map((n) => computeNoteHash(n.content));

  if (isDuplicateNote(incomingHash, authorId, recentSameAuthorHashes, NOTE_DEDUP_WINDOW_SECONDS)) {
    return { data: null, error: "Duplicate note: same content submitted recently." };
  }

  const { error } = await serviceClient
    .from("ticket_note")
    .insert({ ticketId, content, authorId });

  if (error) {
    return { data: null, error: `Database error: ${error.message}` };
  }

  return { data: null, error: null };
}

/**
 * Delete an internal note by id (decision #4 / TI-032 / TI-035).
 *
 * The delete is AUTHOR-ONLY: the note's `authorId` MUST match the session
 * user's Discord id. Non-owners are rejected. Guild isolation is enforced
 * transitively: the note's `ticketId` is resolved first, then the ticket's
 * guild is resolved and authorized via {@link resolveTicketGuild}. An admin of
 * guild A can therefore never delete a note attached to guild B's ticket.
 */
export async function deleteTicketNote(
  noteId: string
): Promise<TicketMutationResult> {
  const serviceClient = await createServiceClient();

  // 1. Resolve the note (need ticketId + authorId for ownership).
  const { data: note, error: noteError } = await serviceClient
    .from("ticket_note")
    .select("ticketId, authorId")
    .eq("id", noteId)
    .single();

  if (noteError) {
    return { data: null, error: `Database error: ${noteError.message}` };
  }
  if (!note) {
    return { data: null, error: "Note not found." };
  }

  const noteRow = note as { ticketId: string; authorId: string };
  const ticketId = noteRow.ticketId;

  // 2. Resolve + authorize the ticket's guild (admin-only).
  const resolved = await resolveTicketGuild(ticketId);
  if ("error" in resolved) {
    return { data: null, error: resolved.error };
  }

  // 3. Author-only ownership check.
  const actorId = await resolveSessionUserId();
  try {
    checkCanDeleteNote(noteRow.authorId, actorId);
  } catch (err) {
    return { data: null, error: (err as Error).message };
  }

  // 4. Delete the note.
  const { error } = await serviceClient
    .from("ticket_note")
    .delete()
    .eq("id", noteId);

  if (error) {
    return { data: null, error: `Database error: ${error.message}` };
  }

  return { data: null, error: null };
}

/**
 * Fetch paginated `ticket_audit` rows for a guild, newest first (TI-038 /
 * TI-021).
 *
 * Auth-gated by {@link verifyGuildAdmin}: only an administrator of the guild
 * may view its audit trail (audit view = admin only). Guild isolation is
 * enforced via `.eq("guildId", guildId)` — audit rows from other guilds can
 * never leak into the result set. Pagination is page-based with
 * {@link AUDIT_PAGE_SIZE} rows per page.
 *
 * @param guildId The guild whose audit rows to read.
 * @param ticketId Optional ticket id filter (narrows to one ticket's history).
 * @param page 1-indexed page number (defaults to 1).
 */
export async function getTicketAudit(
  guildId: string,
  ticketId?: string,
  page: number = 1
): Promise<TicketAuditListResult> {
  const authError = await verifyGuildAdmin(guildId);
  if (authError) {
    return { data: null, error: authError.error };
  }

  const safePage = Math.max(1, Math.floor(page));
  const from = (safePage - 1) * AUDIT_PAGE_SIZE;
  const to = from + AUDIT_PAGE_SIZE - 1;

  const serviceClient = await createServiceClient();
  let chain = serviceClient
    .from("ticket_audit")
    .select("*")
    .eq("guildId", guildId);

  if (ticketId) {
    chain = chain.eq("ticketId", ticketId);
  }

  const { data: rows, error } = await chain
    .order("createdAt", { ascending: false })
    .range(from, to);

  if (error) {
    return { data: null, error: `Database error: ${error.message}` };
  }

  return { data: (rows as TicketAudit[]) ?? [], error: null };
}