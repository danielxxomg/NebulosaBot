import { createServiceClient } from "@/lib/supabase";
import { ConfigForm, type ConfigField } from "@/components/config-form";
import { updateGreetingConfig } from "@/lib/actions/greeting-actions";

export const metadata = {
  title: "Greeting Config — NebulosaBot Dashboard",
};

/**
 * Sensible defaults used when no greeting_config row exists yet.
 */
const GREETING_DEFAULTS = {
  welcomeEnabled: false,
  goodbyeEnabled: false,
  welcomeChannelId: null as string | null,
  goodbyeChannelId: null as string | null,
  welcomeMessage: null as string | null,
  goodbyeMessage: null as string | null,
  welcomeCardEnabled: true,
  goodbyeCardEnabled: true,
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
    .select("*")
    .eq("guildId", guildId)
    .maybeSingle();

  const config = greeting ?? GREETING_DEFAULTS;

  const fields: ConfigField[] = [
    // ── Welcome ──────────────────────────────────────────────
    {
      name: "welcomeEnabled",
      label: "Welcome Messages",
      type: "switch",
      defaultValue: config.welcomeEnabled,
      hint: "Send a welcome message when a member joins.",
    },
    {
      name: "welcomeChannelId",
      label: "Welcome Channel ID",
      type: "text",
      defaultValue: config.welcomeChannelId ?? "",
      placeholder: "123456789012345678",
      hint: "Discord channel ID where welcome messages are sent. Required when enabled.",
    },
    {
      name: "welcomeMessage",
      label: "Welcome Message Template",
      type: "textarea",
      defaultValue: config.welcomeMessage ?? "",
      placeholder:
        "Welcome to {server}, {user}! You are member #{count}.",
      hint: "Use {user}, {server}, and {count} as placeholders. Max 2,000 characters.",
    },
    {
      name: "welcomeCardEnabled",
      label: "Welcome Image Card",
      type: "switch",
      defaultValue: config.welcomeCardEnabled,
      hint: "Generate a custom image card for welcome messages.",
    },
    // ── Goodbye ──────────────────────────────────────────────
    {
      name: "goodbyeEnabled",
      label: "Goodbye Messages",
      type: "switch",
      defaultValue: config.goodbyeEnabled,
      hint: "Send a goodbye message when a member leaves.",
    },
    {
      name: "goodbyeChannelId",
      label: "Goodbye Channel ID",
      type: "text",
      defaultValue: config.goodbyeChannelId ?? "",
      placeholder: "123456789012345678",
      hint: "Discord channel ID where goodbye messages are sent. Required when enabled.",
    },
    {
      name: "goodbyeMessage",
      label: "Goodbye Message Template",
      type: "textarea",
      defaultValue: config.goodbyeMessage ?? "",
      placeholder: "{user} has left the server. We'll miss you!",
      hint: "Use {user} and {server} as placeholders. Max 2,000 characters.",
    },
    {
      name: "goodbyeCardEnabled",
      label: "Goodbye Image Card",
      type: "switch",
      defaultValue: config.goodbyeCardEnabled,
      hint: "Generate a custom image card for goodbye messages.",
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
