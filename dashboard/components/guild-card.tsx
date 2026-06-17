import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import type { DiscordGuild } from "@/lib/types";

interface GuildCardProps {
  guild: DiscordGuild;
}

/**
 * Clickable guild selection card.
 *
 * Renders the guild icon (or a fallback initial) and name.
 * Links to `/guilds/{id}` for per-guild management.
 */
export function GuildCard({ guild }: GuildCardProps) {
  const iconUrl = guild.icon
    ? `https://cdn.discordapp.com/icons/${guild.id}/${guild.icon}.png?size=128`
    : null;

  return (
    <Link href={`/guilds/${guild.id}`} className="group block">
      <Card className="h-full transition-colors hover:bg-accent">
        <CardContent className="flex items-center gap-4 p-4">
          {iconUrl ? (
            <img
              src={iconUrl}
              alt={`${guild.name} icon`}
              className="h-12 w-12 rounded-full object-cover"
              loading="lazy"
            />
          ) : (
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-muted text-lg font-semibold text-muted-foreground">
              {guild.name.charAt(0).toUpperCase()}
            </div>
          )}
          <div className="min-w-0">
            <h3 className="truncate font-semibold group-hover:text-foreground">
              {guild.name}
            </h3>
            <p className="text-sm text-muted-foreground">
              {guild.owner ? "Owner" : "Administrator"}
            </p>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
