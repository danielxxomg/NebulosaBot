import { createServiceClient } from "@/lib/supabase";
import { fetchGuildInfo } from "@/lib/discord";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import Link from "next/link";
import { Settings, Coins, MessageSquareHeart } from "lucide-react";

interface GuildOverviewProps {
  params: Promise<{ guildId: string }>;
}

/**
 * Guild overview page.
 *
 * Fetches the current guild config and Discord guild metadata,
 * then renders summary cards and links to each config section.
 */
export default async function GuildOverviewPage({ params }: GuildOverviewProps) {
  const { guildId } = await params;

  const serviceClient = await createServiceClient();

  // Fetch guild config and Discord metadata in parallel.
  const [{ data: config }, discGuild] = await Promise.all([
    serviceClient
      .from("guild")
      .select(
        "id, prefix, language, modRoleId, logChannelId, logEnabled, welcomeEnabled"
      )
      .eq("id", guildId)
      .single(),
    fetchGuildInfo(guildId).catch(() => null),
  ]);

  if (!config) {
    return (
      <div className="flex flex-col items-center justify-center py-24">
        <h1 className="text-xl font-bold">Guild not found</h1>
        <p className="mt-2 text-muted-foreground">
          This guild is not configured in NebulosaBot.
        </p>
      </div>
    );
  }

  const configSections = [
    {
      title: "General Config",
      description: "Prefix, language, roles, and logging",
      href: `/guilds/${guildId}/config`,
      icon: Settings,
    },
    {
      title: "Economy",
      description: "Daily rewards, XP, and level roles",
      href: `/guilds/${guildId}/economy`,
      icon: Coins,
    },
    {
      title: "Greeting",
      description: "Welcome and goodbye messages",
      href: `/guilds/${guildId}/greeting`,
      icon: MessageSquareHeart,
      status: config.welcomeEnabled ? "Enabled" : "Disabled",
    },
  ];

  return (
    <div>
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold">
          {discGuild?.name ?? `Guild ${guildId}`}
        </h1>
        <p className="mt-1 text-muted-foreground">
          Manage your server&rsquo;s configuration
        </p>
      </div>

      {/* Quick stats */}
      <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Prefix
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="font-mono text-2xl">{config.prefix}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Language
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="font-mono text-2xl">{config.language.toUpperCase()}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Logging
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="font-mono text-2xl">
              {config.logEnabled ? "ON" : "OFF"}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Members
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="font-mono text-2xl">
              {discGuild?.approximate_member_count ?? "—"}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Config section cards */}
      <h2 className="mb-4 text-lg font-semibold">Configuration</h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {configSections.map((section) => {
          const Icon = section.icon;
          return (
            <Link key={section.title} href={section.href}>
              <Card className="h-full transition-colors hover:bg-accent">
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <Icon className="h-5 w-5 text-muted-foreground" />
                    <CardTitle>{section.title}</CardTitle>
                  </div>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">
                    {section.description}
                  </p>
                  {"status" in section && (
                    <p className="mt-2 text-xs font-medium text-primary">
                      {section.status}
                    </p>
                  )}
                </CardContent>
              </Card>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
