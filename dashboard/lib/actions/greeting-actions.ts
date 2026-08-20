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
  const authError = await verifyGuildAdmin(guildId);
  if (authError) return authError;

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

  // 3. Validate.
  if (welcomeEnabled && !welcomeChannelId) {
    return { success: false, error: "Welcome channel is required when welcome messages are enabled.", field: "welcomeChannelId" };
  }
  if (welcomeChannelId && !/^\d{17,20}$/.test(welcomeChannelId)) {
    return { success: false, error: "Welcome channel ID must be a valid Discord snowflake.", field: "welcomeChannelId" };
  }
  if (onboardingChannelId && !/^\d{17,20}$/.test(onboardingChannelId)) {
    return { success: false, error: "Onboarding channel ID must be a valid Discord snowflake.", field: "onboardingChannelId" };
  }

  if (goodbyeEnabled && !goodbyeChannelId) {
    return { success: false, error: "Goodbye channel is required when goodbye messages are enabled.", field: "goodbyeChannelId" };
  }
  if (goodbyeChannelId && !/^\d{17,20}$/.test(goodbyeChannelId)) {
    return { success: false, error: "Goodbye channel ID must be a valid Discord snowflake.", field: "goodbyeChannelId" };
  }

  if (welcomeMessage && welcomeMessage.length > 2000) {
    return { success: false, error: "Welcome message must be 2,000 characters or fewer.", field: "welcomeMessage" };
  }
  if (goodbyeMessage && goodbyeMessage.length > 2000) {
    return { success: false, error: "Goodbye message must be 2,000 characters or fewer.", field: "goodbyeMessage" };
  }

  // 4. Persist to Supabase (UPSERT).
  const serviceClient = await createServiceClient();
  const { error } = await serviceClient
    .from("greeting_config")
    .upsert({
      guildId,
      welcomeEnabled,
      goodbyeEnabled,
      welcomeChannelId,
      goodbyeChannelId,
      onboardingChannelId,
      welcomeMessage,
      goodbyeMessage,
      welcomeCardEnabled,
      goodbyeCardEnabled,
    })
    .eq("guildId", guildId);

  if (error) {
    return { success: false, error: `Database error: ${error.message}` };
  }

  // 5. Revalidate guild-scoped pages.
  revalidatePath(`/guilds/${guildId}`, "layout");

  return { success: true, message: "Greeting configuration saved." };
}
