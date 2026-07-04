"use server";

import { createServerSupabaseClient, createServiceClient } from "@/lib/supabase";
import { fetchUserGuilds, hasAdministratorPerm } from "@/lib/discord";
import type { Ticket, TicketNote } from "@/lib/types";

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
 * Result of a ticket mutation (reopen / transfer / add note / delete note).
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
  | { data: null; error: string };

/** Hard cap on rows returned per request. Pagination is out of scope for v1. */
const TICKET_PAGE_LIMIT = 50;

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
  // 1. Auth re-check (defense-in-depth).
  const authError = await verifyGuildAdmin(guildId);
  if (authError) {
    return { data: null, error: authError.error };
  }

  // 2. Read tickets (service role bypasses RLS; guildId filter enforces isolation).
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
 * Reopen a previously-closed ticket.
 *
 * Sets `status` back to `"open"` and clears `closedAt`. Auth-gated by
 * {@link resolveTicketGuild}: only an administrator of the ticket's guild
 * may reopen it.
 */
export async function reopenTicket(
  ticketId: string
): Promise<TicketMutationResult> {
  const resolved = await resolveTicketGuild(ticketId);
  if ("error" in resolved) {
    return { data: null, error: resolved.error };
  }

  const serviceClient = await createServiceClient();
  const { error } = await serviceClient
    .from("ticket")
    .update({ status: "open", closedAt: null })
    .eq("id", ticketId);

  if (error) {
    return { data: null, error: `Database error: ${error.message}` };
  }

  return { data: null, error: null };
}

/**
 * Transfer a ticket's claim to a different staff member.
 *
 * Updates `claimedBy` to `newClaimedBy`. Auth-gated by
 * {@link resolveTicketGuild}: only an administrator of the ticket's guild
 * may transfer it.
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
    .update({ claimedBy: newClaimedBy })
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
 * The note author is the currently-logged-in Discord user, resolved from the
 * Supabase session's Discord identity (`session.user.identities[0].id`).
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

  // Resolve the author's Discord user id from the auth session.
  const supabase = await createServerSupabaseClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  const authorId =
    session?.user?.identities?.[0]?.id ?? session?.user?.id ?? "unknown";

  const serviceClient = await createServiceClient();
  const { error } = await serviceClient
    .from("ticket_note")
    .insert({ ticketId, content, authorId });

  if (error) {
    return { data: null, error: `Database error: ${error.message}` };
  }

  return { data: null, error: null };
}

/**
 * Delete an internal note by id.
 *
 * Guild isolation is enforced transitively: the note's `ticketId` is resolved
 * first, then the ticket's guild is resolved and authorized via
 * {@link resolveTicketGuild}. An admin of guild A can therefore never delete
 * a note attached to guild B's ticket.
 */
export async function deleteTicketNote(
  noteId: string
): Promise<TicketMutationResult> {
  const serviceClient = await createServiceClient();

  // 1. Resolve the note's ticket.
  const { data: note, error: noteError } = await serviceClient
    .from("ticket_note")
    .select("ticketId")
    .eq("id", noteId)
    .single();

  if (noteError) {
    return { data: null, error: `Database error: ${noteError.message}` };
  }
  if (!note) {
    return { data: null, error: "Note not found." };
  }

  const ticketId = (note as { ticketId: string }).ticketId;

  // 2. Resolve + authorize the ticket's guild.
  const resolved = await resolveTicketGuild(ticketId);
  if ("error" in resolved) {
    return { data: null, error: resolved.error };
  }

  // 3. Delete the note.
  const { error } = await serviceClient
    .from("ticket_note")
    .delete()
    .eq("id", noteId);

  if (error) {
    return { data: null, error: `Database error: ${error.message}` };
  }

  return { data: null, error: null };
}
