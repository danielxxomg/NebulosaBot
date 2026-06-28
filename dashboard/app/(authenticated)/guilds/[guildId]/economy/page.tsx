import { createServiceClient } from "@/lib/supabase";
import { ConfigForm, type ConfigField } from "@/components/config-form";
import { updateEconomyConfig } from "@/lib/actions/economy-actions";

export const metadata = {
  title: "Economy Config — NebulosaBot Dashboard",
};

/**
 * Sensible defaults used when no economy_config row exists yet.
 */
const ECONOMY_DEFAULTS = {
  dailyReward: 100,
  dailyCooldownHours: 24,
  xpPerMessage: 10,
  xpCooldownSeconds: 60,
  levelBaseXp: 100,
  levelMultiplier: 1.5,
  levelRoles: {} as Record<string, string>,
  levelUpChannelId: null as string | null,
};

interface EconomyConfigPageProps {
  params: Promise<{ guildId: string }>;
}

/**
 * Economy configuration page.
 *
 * Edits per-guild economy settings: daily rewards, XP rates,
 * cooldowns, level thresholds, and auto-role assignment.
 */
export default async function EconomyConfigPage({
  params,
}: EconomyConfigPageProps) {
  const { guildId } = await params;

  const serviceClient = await createServiceClient();
  const { data: economy } = await serviceClient
    .from("economy_config")
    .select("*")
    .eq("guildId", guildId)
    .maybeSingle();

  const config = economy ?? ECONOMY_DEFAULTS;

  const fields: ConfigField[] = [
    {
      name: "dailyReward",
      label: "Daily Reward",
      type: "number",
      defaultValue: config.dailyReward,
      hint: "Coins awarded for the daily claim (1–1,000,000).",
      required: true,
    },
    {
      name: "dailyCooldownHours",
      label: "Daily Cooldown (hours)",
      type: "number",
      defaultValue: config.dailyCooldownHours,
      hint: "Hours between daily claims (1–720).",
      required: true,
    },
    {
      name: "xpPerMessage",
      label: "XP per Message",
      type: "number",
      defaultValue: config.xpPerMessage,
      hint: "XP awarded per qualifying message (1–1,000).",
      required: true,
    },
    {
      name: "xpCooldownSeconds",
      label: "XP Cooldown (seconds)",
      type: "number",
      defaultValue: config.xpCooldownSeconds,
      hint: "Seconds between XP awards per member (1–3,600).",
      required: true,
    },
    {
      name: "levelBaseXp",
      label: "Level Base XP",
      type: "number",
      defaultValue: config.levelBaseXp,
      hint: "Base XP required for level 1 (1–1,000,000).",
      required: true,
    },
    {
      name: "levelMultiplier",
      label: "Level Multiplier",
      type: "number",
      defaultValue: config.levelMultiplier,
      hint: "Multiplier for level thresholds (1.0–10.0).",
      required: true,
    },
    {
      name: "levelRoles",
      label: "Level Roles",
      type: "textarea",
      defaultValue: JSON.stringify(config.levelRoles, null, 2),
      placeholder: '{"1": "role_id_1", "5": "role_id_2"}',
      hint: 'JSON mapping of level → Discord role ID. e.g. {"1": "123...", "10": "456..."}. Leave empty for none.',
    },
    {
      name: "levelUpChannelId",
      label: "Level-Up Channel ID",
      type: "text",
      defaultValue: config.levelUpChannelId ?? "",
      placeholder: "123456789012345678",
      hint: "Discord channel ID where level-up announcements are sent.",
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Economy Configuration</h1>
        <p className="mt-1 text-muted-foreground">
          Daily rewards, XP earnings, level thresholds, and auto-role assignment.
        </p>
      </div>
      <ConfigForm
        guildId={guildId}
        action={updateEconomyConfig}
        fields={fields}
      />
    </div>
  );
}
