import { createServerSupabaseClient } from "@/lib/supabase";
import { createServiceClient } from "@/lib/supabase";
import { fetchUserGuilds, hasAdministratorPerm } from "@/lib/discord";
import { GuildCard } from "@/components/guild-card";
import { redirect } from "next/navigation";
import { AlertTriangle, Bot } from "lucide-react";

export const metadata = {
  title: "Guilds — NebulosaBot Dashboard",
};

/**
 * Guild selector — the home page after login.
 *
 * Flow:
 *   1. Verify session (redirect to /login if missing).
 *   2. Fetch Discord user guilds via the OAuth2 provider token.
 *   3. Cross-reference with active guilds in Supabase.
 *   4. Filter to guilds where the user has ADMINISTRATOR permission.
 *   5. Render a grid of GuildCard components.
 */
export default async function GuildSelectorPage() {
  const supabase = await createServerSupabaseClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) {
    redirect("/login");
  }

  const providerToken = session.provider_token;

  // The Discord provider token is required to call the Discord API.
  if (!providerToken) {
    return (
      <div className="flex flex-col items-center justify-center py-24">
        <AlertTriangle className="h-12 w-12 text-destructive" />
        <h1 className="mt-4 text-xl font-bold">Authentication Error</h1>
        <p className="mt-2 text-center text-muted-foreground">
          Discord access token is not available.
          <br />
          Please log out and sign in again.
        </p>
      </div>
    );
  }

  // Fetch the user's Discord guilds and the bot's active guilds in parallel.
  const [discordGuilds, { data: activeGuilds }] = await Promise.all([
    fetchUserGuilds(providerToken),
    createServiceClient()
      .then((client) => client.from("guild").select("id").eq("active", true))
      .then((result) => result),
  ]);

  const botGuildIds = new Set((activeGuilds ?? []).map((g) => g.id));

  // Only show guilds the user administrates AND where the bot is present.
  const authorizedGuilds = discordGuilds.filter(
    (g) => hasAdministratorPerm(g.permissions) && botGuildIds.has(g.id)
  );

  return (
    <div>
      <h1 className="text-2xl font-bold">Select a Guild</h1>
      <p className="mt-2 text-muted-foreground">
        Choose a guild to manage its configuration
      </p>

      {authorizedGuilds.length === 0 ? (
        <div className="mt-12 flex flex-col items-center rounded-lg border border-dashed p-12 text-center">
          <Bot className="h-12 w-12 text-muted-foreground" />
          <h2 className="mt-4 text-lg font-semibold">No authorized guilds found</h2>
          <p className="mt-2 max-w-md text-sm text-muted-foreground">
            You need the <strong>Administrator</strong> permission in a Discord
            server where NebulosaBot is already present. Invite the bot to your
            server first if you haven&rsquo;t already.
          </p>
        </div>
      ) : (
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {authorizedGuilds.map((guild) => (
            <GuildCard key={guild.id} guild={guild} />
          ))}
        </div>
      )}
    </div>
  );
}
