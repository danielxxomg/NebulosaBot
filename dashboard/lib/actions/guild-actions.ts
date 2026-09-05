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
const isValidSnowflake = (value: string | null): boolean => {
  // null/empty is valid (optional field)
  if (!value) {return true;}
  return /^\d{17,20}$/u.test(value);
};

/**
 * Update the guild-level configuration.
 *
 * Validates each field before persisting to Supabase, then revalidates
 * the guild-scoped pages so the UI reflects the latest data.
 */
export const updateGuildConfig = async (guildId: string, formData: FormData): Promise<ActionResult> => {
  // 1. Auth re-check.
  const authError = await verifyGuildAdmin(
    guildId,
    "You must be a server administrator to change guild settings."
  );
  if (authError) {return authError;}

  // 2. Extract and normalize fields.
  const prefix = (formData.get("prefix") as string)?.trim() ?? "";
  const language = (formData.get("language") as string)?.trim().toLowerCase() ?? "";
  const modRoleId = (formData.get("modRoleId") as string)?.trim() || null;
  const logChannelId = (formData.get("logChannelId") as string)?.trim() || null;
  const ticketCategoryId = (formData.get("ticketCategoryId") as string)?.trim() || null;
  const logEnabled = formData.get("logEnabled") === "on";

  // 3. Validate.
  if (!prefix || prefix.length < 1 || prefix.length > 10) {
    return { error: "Prefix must be 1–10 characters.", field: "prefix", success: false };
  }

  if (!VALID_LANGUAGES.has(language)) {
    return { error: `Unsupported language: "${language}".`, field: "language", success: false };
  }

  if (!isValidSnowflake(modRoleId)) {
    return { error: "Mod role ID must be a valid Discord snowflake.", field: "modRoleId", success: false };
  }

  if (!isValidSnowflake(logChannelId)) {
    return { error: "Log channel ID must be a valid Discord snowflake.", field: "logChannelId", success: false };
  }

  if (!isValidSnowflake(ticketCategoryId)) {
    return { error: "Ticket category ID must be a valid Discord snowflake.", field: "ticketCategoryId", success: false };
  }

  // 4. Persist to Supabase.
  const serviceClient = await createServiceClient();
  const { error } = await serviceClient
    .from("guild")
    .update({
      language,
      logChannelId,
      logEnabled,
      modRoleId,
      prefix,
      ticketCategoryId,
    })
    .eq("id", guildId);

  if (error) {
    return { error: `Database error: ${error.message}`, success: false };
  }

  // 5. Revalidate guild-scoped pages.
  revalidatePath(`/guilds/${guildId}`, "layout");

  return { message: "Configuration saved.", success: true };
};
