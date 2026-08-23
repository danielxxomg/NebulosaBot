import { createServiceClient } from "@/lib/supabase";
import { ConfigForm } from '@/components/config-form';
import type { ConfigField } from '@/components/config-form';
import { updateGreetingConfig } from "@/lib/actions/greeting-actions";

export const metadata = {
  title: "Greeting Config — NebulosaBot Dashboard",
};

/**
 * Sensible defaults used when no greeting_config row exists yet.
 * Card toggles default to false to match bot/models/greeting_config.py (spec GC-4).
 */
const GREETING_DEFAULTS = {
  goodbyeCardEnabled: false,
  goodbyeChannelId: null as string | null,
  goodbyeEnabled: false,
  goodbyeMessage: null as string | null,
  onboardingChannelId: null as string | null,
  themeId: null as string | null,
  welcomeCardEnabled: false,
  welcomeChannelId: null as string | null,
  welcomeEnabled: false,
  welcomeMessage: null as string | null,
};

interface GreetingConfigPageProps {
  params: Promise<{ guildId: string }>;
}

/**
 * Greeting configuration page.
 *
 * Edits per-guild welcome and goodbye settings: toggles,
 * target channels, message templates, and image card opt-ins.
 * All fields are submitted together in a single form so that
 * editing one section does not silently reset the other.
 */
export default async function GreetingConfigPage({
  params,
}: GreetingConfigPageProps) {
  const { guildId } = await params;

  const serviceClient = await createServiceClient();
  const { data: greeting } = await serviceClient
    .from("greeting_config")
    .select("guildId, welcomeEnabled, goodbyeEnabled, welcomeChannelId, goodbyeChannelId, onboardingChannelId, welcomeMessage, goodbyeMessage, welcomeCardEnabled, goodbyeCardEnabled, updatedAt, themeId")
    .eq("guildId", guildId)
    .maybeSingle();

  const config = greeting ?? GREETING_DEFAULTS;

  const fields: ConfigField[] = [
    // ── Welcome ──────────────────────────────────────────────
    {
      defaultValue: config.welcomeEnabled,
      hint: "Send a welcome message when a member joins.",
      label: "Welcome Messages",
      name: "welcomeEnabled",
      type: "switch",
    },
    {
      defaultValue: config.welcomeChannelId ?? "",
      hint: "Discord channel ID where welcome messages are sent. Required when enabled.",
      label: "Welcome Channel ID",
      name: "welcomeChannelId",
      placeholder: "123456789012345678",
      type: "text",
    },
    {
      defaultValue: config.onboardingChannelId ?? "",
      hint: "Optional channel mentioned in welcome messages to help new members get started.",
      label: "Onboarding Channel ID",
      name: "onboardingChannelId",
      placeholder: "123456789012345678",
      type: "text",
    },
    {
      defaultValue: config.welcomeMessage ?? "",
      hint: "Use {user}, {server}, and {count} as placeholders. Max 2,000 characters.",
      label: "Welcome Message Template",
      name: "welcomeMessage",
      placeholder:
        "Welcome to {server}, {user}! You are member #{count}.",
      type: "textarea",
    },
    {
      defaultValue: config.welcomeCardEnabled,
      hint: "Generate a custom image card for welcome messages.",
      label: "Welcome Image Card",
      name: "welcomeCardEnabled",
      type: "switch",
    },
    // ── Goodbye ──────────────────────────────────────────────
    {
      defaultValue: config.goodbyeEnabled,
      hint: "Send a goodbye message when a member leaves.",
      label: "Goodbye Messages",
      name: "goodbyeEnabled",
      type: "switch",
    },
    {
      defaultValue: config.goodbyeChannelId ?? "",
      hint: "Discord channel ID where goodbye messages are sent. Required when enabled.",
      label: "Goodbye Channel ID",
      name: "goodbyeChannelId",
      placeholder: "123456789012345678",
      type: "text",
    },
    {
      defaultValue: config.goodbyeMessage ?? "",
      hint: "Use {user} and {server} as placeholders. Max 2,000 characters.",
      label: "Goodbye Message Template",
      name: "goodbyeMessage",
      placeholder: "{user} has left the server. We'll miss you!",
      type: "textarea",
    },
    {
      defaultValue: config.goodbyeCardEnabled,
      hint: "Generate a custom image card for goodbye messages.",
      label: "Goodbye Image Card",
      name: "goodbyeCardEnabled",
      type: "switch",
    },
    // ── Theme ────────────────────────────────────────────────
    {
      defaultValue: (config as { themeId?: string | null }).themeId ?? "",
      hint: "Theme for greeting cards: gaming_neon or default (empty).",
      label: "Greeting Theme",
      name: "themeId",
      placeholder: "gaming_neon or empty for default",
      type: "text",
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Greeting Configuration</h1>
        <p className="mt-1 text-muted-foreground">
          Welcome and goodbye messages with custom templates and image cards.
        </p>
      </div>
      <ConfigForm
        guildId={guildId}
        action={updateGreetingConfig}
        fields={fields}
      />
    </div>
  );
}
