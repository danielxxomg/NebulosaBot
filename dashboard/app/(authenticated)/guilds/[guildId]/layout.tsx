import { Sidebar } from "@/components/sidebar";
import { createServerSupabaseClient } from "@/lib/supabase";
import { createServiceClient } from "@/lib/supabase";
import { fetchUserGuilds, hasAdministratorPerm } from "@/lib/discord";
import { notFound, redirect } from "next/navigation";

interface GuildLayoutProps {
  children: React.ReactNode;
  params: Promise<{ guildId: string }>;
}

/**
 * Per-guild layout.
 *
 * Guards each guild-scoped page with two checks:
 *   1. The guild exists and is active in Supabase.
 *   2. The current user has ADMINISTRATOR permission in that Discord guild.
 *
 * Renders the sidebar with guild-scoped navigation links.
 */
export default async function GuildLayout({ children, params }: GuildLayoutProps) {
  const { guildId } = await params;

  const supabase = await createServerSupabaseClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) {
    redirect("/login");
  }

  const providerToken = session.provider_token;

  if (!providerToken) {
    redirect("/?error=no_provider_token");
  }

  // Verify guild exists and is active.
  const serviceClient = await createServiceClient();
  const { data: guild } = await serviceClient
    .from("guild")
    .select("id, active")
    .eq("id", guildId)
    .single();

  if (!guild || !guild.active) {
    notFound();
  }

  // Verify the current user has admin permission in this guild.
  const userGuilds = await fetchUserGuilds(providerToken);
  const targetGuild = userGuilds.find((g) => g.id === guildId);

  if (!targetGuild || !hasAdministratorPerm(targetGuild.permissions)) {
    redirect("/?error=unauthorized");
  }

  return (
    <div className="flex min-h-[calc(100vh-0px)]">
      <Sidebar guildId={guildId} />
      <main className="flex-1 p-6 md:p-8">{children}</main>
    </div>
  );
}
