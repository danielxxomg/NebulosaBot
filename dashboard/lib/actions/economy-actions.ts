"use server";

import { createServerSupabaseClient, createServiceClient } from "@/lib/supabase";
import { fetchUserGuilds, hasAdministratorPerm } from "@/lib/discord";
import { notifyWebhookSync } from "@/lib/webhook-sync";
import { revalidatePath } from "next/cache";
import type { ActionResult } from "@/lib/types";

/**
 * Re-verify the current user has admin access to the target guild.
 *
 * Called inside every Server Action as defense-in-depth beyond the
 * layout-level permission guard.
 */
async function verifyGuildAdmin(guildId: string): Promise<ActionResult | null> {
  const supabase = await createServerSupabaseClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) {
    return { success: false, error: "Not authenticated." };
  }

  const providerToken = session.provider_token;
  if (!providerToken) {
    return { success: false, error: "Discord token not available. Please re-login." };
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
    return { success: false, error: "You must be a server administrator to change settings." };
  }

  return null; // null = auth passed
}

/**
 * Update the economy configuration for a guild.
 *
 * Uses UPSERT — inserts a new row if one doesn't exist yet, otherwise
 * updates the existing row. All numeric fields are validated for
 * reasonable bounds before persisting.
 */
export async function updateEconomyConfig(
  guildId: string,
  formData: FormData
): Promise<ActionResult> {
  // 1. Auth re-check.
  const authError = await verifyGuildAdmin(guildId);
  if (authError) return authError;

  // 2. Extract numeric fields.
  const dailyReward = parseInt(formData.get("dailyReward") as string, 10);
  const dailyCooldownHours = parseInt(formData.get("dailyCooldownHours") as string, 10);
  const xpPerMessage = parseInt(formData.get("xpPerMessage") as string, 10);
  const xpCooldownSeconds = parseInt(formData.get("xpCooldownSeconds") as string, 10);
  const levelBaseXp = parseInt(formData.get("levelBaseXp") as string, 10);
  const levelMultiplier = parseFloat(formData.get("levelMultiplier") as string);
  const levelUpChannelId = (formData.get("levelUpChannelId") as string)?.trim() || null;

  // Parse levelRoles JSON.
  let levelRoles: Record<string, string> = {};
  const rawLevelRoles = (formData.get("levelRoles") as string)?.trim();
  if (rawLevelRoles) {
    try {
      levelRoles = JSON.parse(rawLevelRoles);
      if (typeof levelRoles !== "object" || Array.isArray(levelRoles)) {
        return { success: false, error: "Level roles must be a JSON object.", field: "levelRoles" };
      }
    } catch {
      return { success: false, error: "Invalid JSON in level roles.", field: "levelRoles" };
    }
  }

  // 3. Validate numeric bounds.
  if (isNaN(dailyReward) || dailyReward < 1 || dailyReward > 1_000_000) {
    return { success: false, error: "Daily reward must be 1–1,000,000.", field: "dailyReward" };
  }
  if (isNaN(dailyCooldownHours) || dailyCooldownHours < 1 || dailyCooldownHours > 720) {
    return { success: false, error: "Daily cooldown must be 1–720 hours.", field: "dailyCooldownHours" };
  }
  if (isNaN(xpPerMessage) || xpPerMessage < 1 || xpPerMessage > 1000) {
    return { success: false, error: "XP per message must be 1–1,000.", field: "xpPerMessage" };
  }
  if (isNaN(xpCooldownSeconds) || xpCooldownSeconds < 1 || xpCooldownSeconds > 3600) {
    return { success: false, error: "XP cooldown must be 1–3,600 seconds.", field: "xpCooldownSeconds" };
  }
  if (isNaN(levelBaseXp) || levelBaseXp < 1 || levelBaseXp > 1_000_000) {
    return { success: false, error: "Level base XP must be 1–1,000,000.", field: "levelBaseXp" };
  }
  if (isNaN(levelMultiplier) || levelMultiplier < 1.0 || levelMultiplier > 10.0) {
    return { success: false, error: "Level multiplier must be 1.0–10.0.", field: "levelMultiplier" };
  }

  // Validate levelUpChannelId snowflake.
  if (levelUpChannelId && !/^\d{17,20}$/.test(levelUpChannelId)) {
    return { success: false, error: "Level-up channel ID must be a valid Discord snowflake.", field: "levelUpChannelId" };
  }

  // 4. Persist to Supabase (UPSERT).
  const serviceClient = await createServiceClient();
  const { error } = await serviceClient
    .from("economy_config")
    .upsert({
      guildId,
      dailyReward,
      dailyCooldownHours,
      xpPerMessage,
      xpCooldownSeconds,
      levelBaseXp,
      levelMultiplier,
      levelRoles,
      levelUpChannelId,
    })
    .eq("guildId", guildId);

  if (error) {
    return { success: false, error: `Database error: ${error.message}` };
  }

  // 5. Notify the bot to drop its RAM cache for this guild (fire-and-forget).
  //    Defense-in-depth: wrap in try/catch so a helper regression can never
  //    fail the config write (Supabase is the source of truth).
  try {
    await notifyWebhookSync(guildId);
  } catch {
    // Swallowed: webhook failure must not fail the write.
  }

  // 6. Revalidate guild-scoped pages.
  revalidatePath(`/guilds/${guildId}`, "layout");

  return { success: true, message: "Economy configuration saved." };
}
