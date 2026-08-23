import { createServiceClient } from "@/lib/supabase";
import { ConfigForm } from '@/components/config-form';
import type { ConfigField } from '@/components/config-form';
import { updateEconomyConfig } from "@/lib/actions/economy-actions";

export const metadata = {
  title: "Economy Config — NebulosaBot Dashboard",
};

/**
 * Sensible defaults used when no economy_config row exists yet.
 */
const ECONOMY_DEFAULTS = {
  dailyCooldownHours: 24,
  dailyReward: 100,
  levelBaseXp: 100,
  levelMultiplier: 1.5,
  levelRoles: {} as Record<string, string>,
  levelUpChannelId: null as string | null,
  xpCooldownSeconds: 60,
  xpPerMessage: 10,
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
    .select("guildId, dailyReward, dailyCooldownHours, xpPerMessage, xpCooldownSeconds, levelBaseXp, levelMultiplier, levelRoles, levelUpChannelId")
    .eq("guildId", guildId)
    .maybeSingle();

  const config = economy ?? ECONOMY_DEFAULTS;

  const fields: ConfigField[] = [
    {
      defaultValue: config.dailyReward,
      hint: "Coins awarded for the daily claim (1–1,000,000).",
      label: "Daily Reward",
      name: "dailyReward",
      required: true,
      type: "number",
    },
    {
      defaultValue: config.dailyCooldownHours,
      hint: "Hours between daily claims (1–720).",
      label: "Daily Cooldown (hours)",
      name: "dailyCooldownHours",
      required: true,
      type: "number",
    },
    {
      defaultValue: config.xpPerMessage,
      hint: "XP awarded per qualifying message (1–1,000).",
      label: "XP per Message",
      name: "xpPerMessage",
      required: true,
      type: "number",
    },
    {
      defaultValue: config.xpCooldownSeconds,
      hint: "Seconds between XP awards per member (1–3,600).",
      label: "XP Cooldown (seconds)",
      name: "xpCooldownSeconds",
      required: true,
      type: "number",
    },
    {
      defaultValue: config.levelBaseXp,
      hint: "Base XP required for level 1 (1–1,000,000).",
      label: "Level Base XP",
      name: "levelBaseXp",
      required: true,
      type: "number",
    },
    {
      defaultValue: config.levelMultiplier,
      hint: "Multiplier for level thresholds (1.0–10.0).",
      label: "Level Multiplier",
      name: "levelMultiplier",
      required: true,
      type: "number",
    },
    {
      defaultValue: JSON.stringify(config.levelRoles, null, 2),
      hint: 'JSON mapping of level → Discord role ID. e.g. {"1": "123...", "10": "456..."}. Leave empty for none.',
      label: "Level Roles",
      name: "levelRoles",
      placeholder: '{"1": "role_id_1", "5": "role_id_2"}',
      type: "textarea",
    },
    {
      defaultValue: config.levelUpChannelId ?? "",
      hint: "Discord channel ID where level-up announcements are sent.",
      label: "Level-Up Channel ID",
      name: "levelUpChannelId",
      placeholder: "123456789012345678",
      type: "text",
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
