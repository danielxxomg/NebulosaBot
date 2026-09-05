import { createServerSupabaseClient, createServiceClient } from "@/lib/supabase";
import { fetchUserGuilds, hasAdministratorPerm } from "@/lib/discord";
import type { ActionResult } from "@/lib/types";

/**
 * Shared guard: re-verify the current user has admin access to the target guild.
 *
 * Single definition — 4 dashboard action modules import this instead of redefining.
 * The caller supplies its domain-specific admin error string so the guard
 * behavior is identical across domains except for the message.
 */
export const verifyGuildAdmin = async (guildId: string, adminError = "You must be a server administrator to change settings."): Promise<{ success: false; error: string } | null> => {
  const supabase = await createServerSupabaseClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) {
    return { error: "Not authenticated.", success: false };
  }

  const providerToken = session.provider_token;
  if (!providerToken) {
    return { error: "Discord token not available. Please re-login.", success: false };
  }

  const serviceClient = await createServiceClient();
  const { data: guild } = await serviceClient.from("guild").select("active").eq("id", guildId).single();

  if (!guild || !guild.active) {
    return { error: "Guild not found or inactive.", success: false };
  }

  const userGuilds = await fetchUserGuilds(providerToken);
  const target = userGuilds.find((g) => g.id === guildId);

  if (!target || !hasAdministratorPerm(target.permissions)) {
    return { error: adminError, success: false };
  }

  return null;
};
