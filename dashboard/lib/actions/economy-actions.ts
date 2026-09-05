"use server";

import { createServiceClient } from "@/lib/supabase";
import { verifyGuildAdmin } from "@/lib/guards";
import { revalidatePath } from "next/cache";
import type { ActionResult } from "@/lib/types";

/** Discord snowflake: 17-20 digits. */
const SNOWFLAKE_RE = /^\d{17,20}$/u;

/**
 * Inclusive integer-bound check. Returns the field error when the value is
 * NaN or outside [min, max]; null when valid.
 */
const checkIntBound = (
  value: number,
  min: number,
  max: number,
  message: string,
  field: string
): { error: string; field: string; success: false } | null =>
  Number.isNaN(value) || value < min || value > max
    ? { error: message, field, success: false }
    : null;

/**
 * Update the economy configuration for a guild.
 *
 * Uses UPSERT — inserts a new row if one doesn't exist yet, otherwise
 * updates the existing row. All numeric fields are validated for
 * reasonable bounds before persisting.
 */
export const updateEconomyConfig = async (guildId: string, formData: FormData): Promise<ActionResult> => {
  // 1. Auth re-check.
  const authError = await verifyGuildAdmin(
    guildId,
    "You must be a server administrator to change economy settings."
  );
  if (authError) {return authError;}

  // 2. Extract numeric fields.
  const dailyReward = Math.trunc(Number(formData.get("dailyReward") as string));
  const dailyCooldownHours = Math.trunc(Number(formData.get("dailyCooldownHours") as string));
  const xpPerMessage = Math.trunc(Number(formData.get("xpPerMessage") as string));
  const xpCooldownSeconds = Math.trunc(Number(formData.get("xpCooldownSeconds") as string));
  const levelBaseXp = Math.trunc(Number(formData.get("levelBaseXp") as string));
  const levelMultiplier = Number(formData.get("levelMultiplier") as string);
  const levelUpChannelId = (formData.get("levelUpChannelId") as string)?.trim() || null;

  // Parse levelRoles JSON.
  let levelRoles: Record<string, string> = {};
  const rawLevelRoles = (formData.get("levelRoles") as string)?.trim();
  if (rawLevelRoles) {
    try {
      levelRoles = JSON.parse(rawLevelRoles);
      if (typeof levelRoles !== "object" || Array.isArray(levelRoles)) {
        return { error: "Level roles must be a JSON object.", field: "levelRoles", success: false };
      }
    } catch {
      return { error: "Invalid JSON in level roles.", field: "levelRoles", success: false };
    }
  }

  // 3. Validate numeric bounds + snowflake (error strings preserved verbatim).
  const boundError =
    checkIntBound(dailyReward, 1, 1_000_000, "Daily reward must be 1–1,000,000.", "dailyReward") ??
    checkIntBound(dailyCooldownHours, 1, 720, "Daily cooldown must be 1–720 hours.", "dailyCooldownHours") ??
    checkIntBound(xpPerMessage, 1, 1000, "XP per message must be 1–1,000.", "xpPerMessage") ??
    checkIntBound(xpCooldownSeconds, 1, 3600, "XP cooldown must be 1–3,600 seconds.", "xpCooldownSeconds") ??
    checkIntBound(levelBaseXp, 1, 1_000_000, "Level base XP must be 1–1,000,000.", "levelBaseXp") ??
    checkIntBound(levelMultiplier, 1, 10, "Level multiplier must be 1.0–10.0.", "levelMultiplier") ??
    (levelUpChannelId && !SNOWFLAKE_RE.test(levelUpChannelId)
      ? { error: "Level-up channel ID must be a valid Discord snowflake.", field: "levelUpChannelId", success: false }
      : null);
  if (boundError) {return boundError;}

  // 4. Persist to Supabase (UPSERT).
  const serviceClient = await createServiceClient();
  const { error } = await serviceClient
    .from("economy_config")
    .upsert({
      dailyCooldownHours,
      dailyReward,
      guildId,
      levelBaseXp,
      levelMultiplier,
      levelRoles,
      levelUpChannelId,
      xpCooldownSeconds,
      xpPerMessage,
    })
    .eq("guildId", guildId);

  if (error) {
    return { error: `Database error: ${error.message}`, success: false };
  }

  // 5. Revalidate guild-scoped pages.
  revalidatePath(`/guilds/${guildId}`, "layout");

  return { message: "Economy configuration saved.", success: true };
};
