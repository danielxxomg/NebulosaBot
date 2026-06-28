import { createServiceClient } from "@/lib/supabase";
import { ConfigForm, type ConfigField } from "@/components/config-form";
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
      name: "prefix",
      label: "Command Prefix",
      type: "text",
      defaultValue: guild.prefix,
      placeholder: "nb!",
      hint: "1–10 characters. Used to invoke bot commands.",
      required: true,
    },
    {
      name: "language",
      label: "Language",
      type: "text",
      defaultValue: guild.language,
      placeholder: "en",
      hint: "Supported: en, es, pt, fr, de, it, ja, ko, ru, zh.",
      required: true,
    },
    {
      name: "modRoleId",
      label: "Moderator Role ID",
      type: "text",
      defaultValue: guild.modRoleId ?? "",
      placeholder: "123456789012345678",
      hint: "Discord role ID for server moderators.",
    },
    {
      name: "logChannelId",
      label: "Log Channel ID",
      type: "text",
      defaultValue: guild.logChannelId ?? "",
      placeholder: "123456789012345678",
      hint: "Discord channel ID where audit/action logs are sent.",
    },
    {
      name: "ticketCategoryId",
      label: "Ticket Category ID",
      type: "text",
      defaultValue: guild.ticketCategoryId ?? "",
      placeholder: "UUID",
      hint: "Default ticket category UUID for new tickets.",
    },
    {
      name: "logEnabled",
      label: "Enable Logging",
      type: "switch",
      defaultValue: guild.logEnabled,
      hint: "When enabled, bot actions are logged to the audit channel.",
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
