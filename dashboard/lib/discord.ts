import type { DiscordGuild } from "@/lib/types";

const DISCORD_API_BASE = "https://discord.com/api/v10";

// Discord API rate limit: 5 requests per second per token (global).
// We cache responses for 60 seconds to avoid hitting limits.
interface CacheEntry<T> {
  data: T;
  expiresAt: number;
}

// Simple in-memory cache.
const cache = new Map<string, CacheEntry<unknown>>();

function getCached<T>(key: string): T | null {
  const entry = cache.get(key) as CacheEntry<T> | undefined;
  if (!entry) return null;
  if (Date.now() > entry.expiresAt) {
    cache.delete(key);
    return null;
  }
  return entry.data;
}

function setCache<T>(key: string, data: T, ttlMs = 60_000): void {
  cache.set(key, { data, expiresAt: Date.now() + ttlMs });
}

/**
 * Fetch the list of guilds the authenticated user belongs to.
 *
 * @param accessToken - Discord OAuth2 access token.
 * @returns Filtered list of guilds where the bot is expected to be present.
 */
export async function fetchUserGuilds(
  accessToken: string
): Promise<DiscordGuild[]> {
  const cacheKey = `guilds:${accessToken.slice(-16)}`;

  const cached = getCached<DiscordGuild[]>(cacheKey);
  if (cached) return cached;

  const res = await fetch(`${DISCORD_API_BASE}/users/@me/guilds`, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  });

  if (!res.ok) {
    throw new Error(`Discord API error: ${res.status} ${res.statusText}`);
  }

  const guilds: DiscordGuild[] = await res.json();
  setCache(cacheKey, guilds);
  return guilds;
}

/**
 * Fetch information about a specific guild.
 *
 * Requires the bot token (not user token) for guild-level access.
 *
 * @param guildId - Discord guild ID.
 * @returns Guild info with name, icon, owner, member count, etc.
 */
export async function fetchGuildInfo(guildId: string): Promise<{
  id: string;
  name: string;
  icon: string | null;
  owner_id: string;
  approximate_member_count?: number;
}> {
  const cacheKey = `guild:${guildId}`;

  const cached = getCached<ReturnType<typeof fetchGuildInfo>>(cacheKey);
  if (cached) return cached;

  const res = await fetch(`${DISCORD_API_BASE}/guilds/${guildId}`, {
    headers: {
      Authorization: `Bot ${process.env.DISCORD_BOT_TOKEN}`,
    },
  });

  if (!res.ok) {
    throw new Error(`Discord API error: ${res.status} ${res.statusText}`);
  }

  const guild = await res.json();
  setCache(cacheKey, guild);
  return guild;
}

/**
 * Check if a user has the ADMINISTRATOR permission in a guild.
 *
 * @param permissions - String-encoded permission bitfield from Discord API.
 * @returns True if the ADMINISTRATOR bit (0x8) is set.
 */
export function hasAdministratorPerm(permissions: string): boolean {
  const permsBigInt = BigInt(permissions);
  const ADMINISTRATOR = BigInt(0x8);
  return (permsBigInt & ADMINISTRATOR) === ADMINISTRATOR;
}
