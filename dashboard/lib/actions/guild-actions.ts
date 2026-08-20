"use server";

import { createServiceClient } from "@/lib/supabase";
import { verifyGuildAdmin } from "@/lib/guards";
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

  // 5. Revalidate guild-scoped pages.
  revalidatePath(`/guilds/${guildId}`, "layout");

  return { success: true, message: "Configuration saved." };
}
