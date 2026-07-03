"use server";

import { createServerSupabaseClient, createServiceClient } from "@/lib/supabase";
import { fetchUserGuilds, hasAdministratorPerm } from "@/lib/discord";
import { notifyWebhookSync } from "@/lib/webhook-sync";
import { revalidatePath } from "next/cache";
import type { ActionResult } from "@/lib/types";

/**
 * Valid language codes the bot supports.
 */
const VALID_LANGUAGES = new Set([
  "en", "es", "pt", "fr", "de", "it", "ja", "ko", "ru", "zh",
]);

/**
 * Validate that a string looks like a Discord snowflake (17-20 digit number).
 */
function isValidSnowflake(value: string | null): boolean {
  if (!value) return true; // null/empty is valid (optional field)
  return /^\d{17,20}$/.test(value);
}

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
 * Update the guild-level configuration.
 *
 * Validates each field before persisting to Supabase, then revalidates
 * the guild-scoped pages so the UI reflects the latest data.
 */
export async function updateGuildConfig(
  guildId: string,
  formData: FormData
): Promise<ActionResult> {
  // 1. Auth re-check.
  const authError = await verifyGuildAdmin(guildId);
  if (authError) return authError;

  // 2. Extract and normalize fields.
  const prefix = (formData.get("prefix") as string)?.trim() ?? "";
  const language = (formData.get("language") as string)?.trim().toLowerCase() ?? "";
  const modRoleId = (formData.get("modRoleId") as string)?.trim() || null;
  const logChannelId = (formData.get("logChannelId") as string)?.trim() || null;
  const ticketCategoryId = (formData.get("ticketCategoryId") as string)?.trim() || null;
  const logEnabled = formData.get("logEnabled") === "on";

  // 3. Validate.
  if (!prefix || prefix.length < 1 || prefix.length > 10) {
    return { success: false, error: "Prefix must be 1–10 characters.", field: "prefix" };
  }

  if (!VALID_LANGUAGES.has(language)) {
    return { success: false, error: `Unsupported language: "${language}".`, field: "language" };
  }

  if (!isValidSnowflake(modRoleId)) {
    return { success: false, error: "Mod role ID must be a valid Discord snowflake.", field: "modRoleId" };
  }

  if (!isValidSnowflake(logChannelId)) {
    return { success: false, error: "Log channel ID must be a valid Discord snowflake.", field: "logChannelId" };
  }

  if (!isValidSnowflake(ticketCategoryId)) {
    return { success: false, error: "Ticket category ID must be a valid Discord snowflake.", field: "ticketCategoryId" };
  }

  // 4. Persist to Supabase.
  const serviceClient = await createServiceClient();
  const { error } = await serviceClient
    .from("guild")
    .update({
      prefix,
      language,
      modRoleId,
      logChannelId,
      ticketCategoryId,
      logEnabled,
    })
    .eq("id", guildId);

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

  return { success: true, message: "Configuration saved." };
}
