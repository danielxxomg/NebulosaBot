"use server";

import { createServiceClient } from "@/lib/supabase";
import { verifyGuildAdmin } from "@/lib/guards";
import { revalidatePath } from "next/cache";
import type { ActionResult } from "@/lib/types";

/** Discord snowflake: 17-20 digits. */
const SNOWFLAKE_RE = /^\d{17,20}$/u;

/** Field-level validation failure. */
interface FieldError {
  error: string;
  field: string;
  success: false;
}

/** Read a checkbox-style form field ("on" when checked). */
const checkbox = (formData: FormData, name: string): boolean =>
  formData.get(name) === "on";

/** Read a text field, trimming to null when absent/blank. */
const textField = (formData: FormData, name: string): string | null =>
  (formData.get(name) as string)?.trim() || null;

/** Required-when-enabled check for a channel selection. */
const checkRequiredWhen = (
  enabled: boolean,
  value: string | null,
  message: string,
  field: string
): FieldError | null =>
  enabled && !value ? { error: message, field, success: false } : null;

/** Snowflake check: null when unset or valid; the field error otherwise. */
const checkSnowflake = (value: string | null, label: string, field: string): FieldError | null =>
  value && !SNOWFLAKE_RE.test(value)
    ? { error: `${label} must be a valid Discord snowflake.`, field, success: false }
    : null;

/** 2,000-character cap for greeting messages. */
const checkMessageCap = (value: string | null, label: string, field: string): FieldError | null =>
  value && value.length > 2000
    ? { error: `${label} must be 2,000 characters or fewer.`, field, success: false }
    : null;

/**
 * Update the greeting (welcome/goodbye) configuration for a guild.
 *
 * Uses UPSERT — inserts a new row if one doesn't exist yet, otherwise
 * updates the existing row. Channel IDs are validated as Discord snowflakes,
 * and message lengths are capped to prevent abuse.
 */
export const updateGreetingConfig = async (guildId: string, formData: FormData): Promise<ActionResult> => {
  // 1. Auth re-check.
  const authError = await verifyGuildAdmin(
    guildId,
    "You must be a server administrator to change greeting settings."
  );
  if (authError) {return authError;}

  // 2. Extract fields (checkbox -> boolean, text -> trimmed-or-null).
  const welcomeEnabled = checkbox(formData, "welcomeEnabled");
  const goodbyeEnabled = checkbox(formData, "goodbyeEnabled");
  const welcomeChannelId = textField(formData, "welcomeChannelId");
  const goodbyeChannelId = textField(formData, "goodbyeChannelId");
  const onboardingChannelId = textField(formData, "onboardingChannelId");
  const welcomeMessage = textField(formData, "welcomeMessage");
  const goodbyeMessage = textField(formData, "goodbyeMessage");
  const welcomeCardEnabled = checkbox(formData, "welcomeCardEnabled");
  const goodbyeCardEnabled = checkbox(formData, "goodbyeCardEnabled");
  // Theme whitelist: only the neon preset is selectable in v1.
  const themeId = textField(formData, "themeId") === "gaming_neon" ? "gaming_neon" : null;

  // 3. Validate (error strings preserved verbatim; order kept: welcome
  // required -> welcome/onboarding snowflake -> goodbye required -> goodbye
  // snowflake -> message caps).
  const validationError: FieldError | null =
    checkRequiredWhen(welcomeEnabled, welcomeChannelId, "Welcome channel is required when welcome messages are enabled.", "welcomeChannelId") ??
    checkSnowflake(welcomeChannelId, "Welcome channel ID", "welcomeChannelId") ??
    checkSnowflake(onboardingChannelId, "Onboarding channel ID", "onboardingChannelId") ??
    checkRequiredWhen(goodbyeEnabled, goodbyeChannelId, "Goodbye channel is required when goodbye messages are enabled.", "goodbyeChannelId") ??
    checkSnowflake(goodbyeChannelId, "Goodbye channel ID", "goodbyeChannelId") ??
    checkMessageCap(welcomeMessage, "Welcome message", "welcomeMessage") ??
    checkMessageCap(goodbyeMessage, "Goodbye message", "goodbyeMessage");
  if (validationError) {return validationError;}

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
};
