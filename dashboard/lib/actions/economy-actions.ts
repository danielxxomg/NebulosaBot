"use server";

import { createServiceClient } from "@/lib/supabase";
import { verifyGuildAdmin } from "@/lib/guards";
import { revalidatePath } from "next/cache";
import type { ActionResult } from "@/lib/types";

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
  const authError = await verifyGuildAdmin(
    guildId,
    "You must be a server administrator to change economy settings."
  );
  if (authError) {return authError;}

  // 2. Extract numeric fields.
  const dailyReward = Number.parseInt(formData.get("dailyReward") as string, 10);
  const dailyCooldownHours = Number.parseInt(formData.get("dailyCooldownHours") as string, 10);
  const xpPerMessage = Number.parseInt(formData.get("xpPerMessage") as string, 10);
  const xpCooldownSeconds = Number.parseInt(formData.get("xpCooldownSeconds") as string, 10);
  const levelBaseXp = Number.parseInt(formData.get("levelBaseXp") as string, 10);
  const levelMultiplier = Number.parseFloat(formData.get("levelMultiplier") as string);
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

  // 3. Validate numeric bounds.
  if (isNaN(dailyReward) || dailyReward < 1 || dailyReward > 1_000_000) {
    return { error: "Daily reward must be 1–1,000,000.", field: "dailyReward", success: false };
  }
  if (isNaN(dailyCooldownHours) || dailyCooldownHours < 1 || dailyCooldownHours > 720) {
    return { error: "Daily cooldown must be 1–720 hours.", field: "dailyCooldownHours", success: false };
  }
  if (isNaN(xpPerMessage) || xpPerMessage < 1 || xpPerMessage > 1000) {
    return { error: "XP per message must be 1–1,000.", field: "xpPerMessage", success: false };
  }
  if (isNaN(xpCooldownSeconds) || xpCooldownSeconds < 1 || xpCooldownSeconds > 3600) {
    return { error: "XP cooldown must be 1–3,600 seconds.", field: "xpCooldownSeconds", success: false };
  }
  if (isNaN(levelBaseXp) || levelBaseXp < 1 || levelBaseXp > 1_000_000) {
    return { error: "Level base XP must be 1–1,000,000.", field: "levelBaseXp", success: false };
  }
  if (isNaN(levelMultiplier) || levelMultiplier < 1 || levelMultiplier > 10) {
    return { error: "Level multiplier must be 1.0–10.0.", field: "levelMultiplier", success: false };
  }

  // Validate levelUpChannelId snowflake.
  if (levelUpChannelId && !/^\d{17,20}$/u.test(levelUpChannelId)) {
    return { error: "Level-up channel ID must be a valid Discord snowflake.", field: "levelUpChannelId", success: false };
  }

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
}
