"use server";

import { createServiceClient } from "@/lib/supabase";
import { verifyGuildAdmin } from "@/lib/guards";
import { revalidatePath } from "next/cache";
import type { ActionResult } from "@/lib/types";

/**
 * Update the greeting (welcome/goodbye) configuration for a guild.
 *
 * Uses UPSERT — inserts a new row if one doesn't exist yet, otherwise
 * updates the existing row. Channel IDs are validated as Discord snowflakes,
 * and message lengths are capped to prevent abuse.
 */
export async function updateGreetingConfig(
  guildId: string,
  formData: FormData
): Promise<ActionResult> {
  // 1. Auth re-check.
  const authError = await verifyGuildAdmin(
    guildId,
    "You must be a server administrator to change greeting settings."
  );
  if (authError) {return authError;}

  // 2. Extract fields.
  const welcomeEnabled = formData.get("welcomeEnabled") === "on";
  const goodbyeEnabled = formData.get("goodbyeEnabled") === "on";
  const welcomeChannelId = (formData.get("welcomeChannelId") as string)?.trim() || null;
  const goodbyeChannelId = (formData.get("goodbyeChannelId") as string)?.trim() || null;
  const onboardingChannelId = (formData.get("onboardingChannelId") as string)?.trim() || null;
  const welcomeMessage = (formData.get("welcomeMessage") as string)?.trim() || null;
  const goodbyeMessage = (formData.get("goodbyeMessage") as string)?.trim() || null;
  const welcomeCardEnabled = formData.get("welcomeCardEnabled") === "on";
  const goodbyeCardEnabled = formData.get("goodbyeCardEnabled") === "on";
  const rawThemeId = (formData.get("themeId") as string)?.trim() || null;
  const themeId = rawThemeId === "gaming_neon" ? "gaming_neon" : null;

  // 3. Validate.
  if (welcomeEnabled && !welcomeChannelId) {
    return { error: "Welcome channel is required when welcome messages are enabled.", field: "welcomeChannelId", success: false };
  }
  if (welcomeChannelId && !/^\d{17,20}$/u.test(welcomeChannelId)) {
    return { error: "Welcome channel ID must be a valid Discord snowflake.", field: "welcomeChannelId", success: false };
  }
  if (onboardingChannelId && !/^\d{17,20}$/u.test(onboardingChannelId)) {
    return { error: "Onboarding channel ID must be a valid Discord snowflake.", field: "onboardingChannelId", success: false };
  }

  if (goodbyeEnabled && !goodbyeChannelId) {
    return { error: "Goodbye channel is required when goodbye messages are enabled.", field: "goodbyeChannelId", success: false };
  }
  if (goodbyeChannelId && !/^\d{17,20}$/u.test(goodbyeChannelId)) {
    return { error: "Goodbye channel ID must be a valid Discord snowflake.", field: "goodbyeChannelId", success: false };
  }

  if (welcomeMessage && welcomeMessage.length > 2000) {
    return { error: "Welcome message must be 2,000 characters or fewer.", field: "welcomeMessage", success: false };
  }
  if (goodbyeMessage && goodbyeMessage.length > 2000) {
    return { error: "Goodbye message must be 2,000 characters or fewer.", field: "goodbyeMessage", success: false };
  }

  // 4. Persist to Supabase (UPSERT).
  const serviceClient = await createServiceClient();
  const { error } = await serviceClient
    .from("greeting_config")
    .upsert({
      goodbyeCardEnabled,
      goodbyeChannelId,
      goodbyeEnabled,
      goodbyeMessage,
      guildId,
      onboardingChannelId,
      themeId,
      welcomeCardEnabled,
      welcomeChannelId,
      welcomeEnabled,
      welcomeMessage,
    })
    .eq("guildId", guildId);

  if (error) {
    return { error: `Database error: ${error.message}`, success: false };
  }

  // 5. Revalidate guild-scoped pages.
  revalidatePath(`/guilds/${guildId}`, "layout");

  return { message: "Greeting configuration saved.", success: true };
}
