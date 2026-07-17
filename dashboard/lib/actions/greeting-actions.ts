"use server";

import { createServerSupabaseClient, createServiceClient } from "@/lib/supabase";
import { fetchUserGuilds, hasAdministratorPerm } from "@/lib/discord";
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
