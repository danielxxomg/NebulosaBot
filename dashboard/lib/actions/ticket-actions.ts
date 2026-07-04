"use server";

import { createServerSupabaseClient, createServiceClient } from "@/lib/supabase";
import { fetchUserGuilds, hasAdministratorPerm } from "@/lib/discord";
import type { Ticket } from "@/lib/types";

/**
 * Result of fetching a guild's tickets.
 *
 * - Success: `{ data: Ticket[], error: null }`
 * - Auth or database failure: `{ data: null, error: string }`
 */
export type TicketListResult =
  | { data: Ticket[]; error: null }
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
