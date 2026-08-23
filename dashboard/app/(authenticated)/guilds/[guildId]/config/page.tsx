import { createServiceClient } from "@/lib/supabase";
import { ConfigForm } from '@/components/config-form';
import type { ConfigField } from '@/components/config-form';
import { updateGuildConfig } from "@/lib/actions/guild-actions";

export const metadata = {
  title: "General Config — NebulosaBot Dashboard",
};

interface GuildConfigPageProps {
  params: Promise<{ guildId: string }>;
}

/**
 * General guild configuration page.
 *
 * Edits the core guild settings: prefix, language, moderator role,
 * logging channel, ticket category, and whether logging is enabled.
 */
export default async function GuildConfigPage({ params }: GuildConfigPageProps) {
  const { guildId } = await params;

  const serviceClient = await createServiceClient();
  const { data: guild } = await serviceClient
    .from("guild")
    .select(
      "id, prefix, language, modRoleId, logChannelId, ticketCategoryId, logEnabled"
    )
    .eq("id", guildId)
    .single();

  if (!guild) {
    return (
      <div className="flex flex-col items-center justify-center py-24">
        <h1 className="text-xl font-bold">Guild not found</h1>
        <p className="mt-2 text-muted-foreground">
          This guild is not configured in NebulosaBot.
        </p>
      </div>
    );
  }

  const fields: ConfigField[] = [
    {
      defaultValue: guild.prefix,
      hint: "1–10 characters. Used to invoke bot commands.",
      label: "Command Prefix",
      name: "prefix",
      placeholder: "nb!",
      required: true,
      type: "text",
    },
    {
      defaultValue: guild.language,
      hint: "Supported: en, es, pt, fr, de, it, ja, ko, ru, zh.",
      label: "Language",
      name: "language",
      placeholder: "en",
      required: true,
      type: "text",
    },
    {
      defaultValue: guild.modRoleId ?? "",
      hint: "Discord role ID for server moderators.",
      label: "Moderator Role ID",
      name: "modRoleId",
      placeholder: "123456789012345678",
      type: "text",
    },
    {
      defaultValue: guild.logChannelId ?? "",
      hint: "Discord channel ID where audit/action logs are sent.",
      label: "Log Channel ID",
      name: "logChannelId",
      placeholder: "123456789012345678",
      type: "text",
    },
    {
      defaultValue: guild.ticketCategoryId ?? "",
      label: "Discord Category Channel ID (right-click \u2192 Copy Channel ID)",
      name: "ticketCategoryId",
      placeholder: "123456789012345678",
      type: "text",
    },
    {
      defaultValue: guild.logEnabled,
      hint: "When enabled, bot actions are logged to the audit channel.",
      label: "Enable Logging",
      name: "logEnabled",
      type: "switch",
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">General Configuration</h1>
        <p className="mt-1 text-muted-foreground">
          Core guild settings — prefix, language, roles, and logging.
        </p>
      </div>
      <ConfigForm
        guildId={guildId}
        action={updateGuildConfig}
        fields={fields}
      />
    </div>
  );
}
