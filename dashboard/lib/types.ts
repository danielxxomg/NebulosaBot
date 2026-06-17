/**
 * TypeScript interfaces mirroring the Supabase database schema (camelCase keys).
 *
 * These types correspond to the Python dataclasses in bot/models/ and the
 * Postgres table definitions from Migration 001/002.
 */

// ── Guild ────────────────────────────────────────────────────────────────

export interface GuildConfig {
  /** Discord guild ID (primary key). */
  id: string;
  /** Command prefix for this guild. */
  prefix: string;
  /** Language code (e.g., "es", "en"). */
  language: string;
  /** Discord role ID for moderators. */
  modRoleId: string | null;
  /** Discord channel ID for audit/action logs. */
  logChannelId: string | null;
  /** Default ticket category ID. */
  ticketCategoryId: string | null;
  /** Ticket panel embed message ID. */
  ticketPanelMessageId: string | null;
  /** Ticket panel send channel ID. */
  ticketPanelChannelId: string | null;
  /** Whether audit logging is enabled. */
  logEnabled: boolean;
  /** Whether welcome messages are enabled. */
  welcomeEnabled: boolean;
  /** Whether the guild is active (not soft-deleted). */
  active: boolean;
}

// ── Economy Config ───────────────────────────────────────────────────────

export interface EconomyConfig {
  /** Discord guild ID (primary key, FK → guild.id). */
  guildId: string;
  /** Coins awarded for the daily claim. */
  dailyReward: number;
  /** Hours between daily claims. */
  dailyCooldownHours: number;
  /** XP awarded per qualifying message. */
  xpPerMessage: number;
  /** Seconds between XP awards per member. */
  xpCooldownSeconds: number;
  /** Base XP required for level 1. */
  levelBaseXp: number;
  /** Exponential multiplier for level thresholds. */
  levelMultiplier: number;
  /** Mapping of level → role ID for auto-role assignment. */
  levelRoles: Record<string, string>;
  /** Channel ID where level-up messages are sent. */
  levelUpChannelId: string | null;
}

// ── Greeting Config ──────────────────────────────────────────────────────

export interface GreetingConfig {
  /** Discord guild ID (primary key, FK → guild.id). */
  guildId: string;
  /** Whether welcome messages are enabled. */
  welcomeEnabled: boolean;
  /** Whether goodbye messages are enabled. */
  goodbyeEnabled: boolean;
  /** Channel ID for welcome messages. */
  welcomeChannelId: string | null;
  /** Channel ID for goodbye messages. */
  goodbyeChannelId: string | null;
  /** Template for welcome messages. */
  welcomeMessage: string | null;
  /** Template for goodbye messages. */
  goodbyeMessage: string | null;
  /** Whether welcome image cards are generated. */
  welcomeCardEnabled: boolean;
  /** Whether goodbye image cards are generated. */
  goodbyeCardEnabled: boolean;
}

// ── Member ───────────────────────────────────────────────────────────────

export interface Member {
  /** Discord guild ID (composite PK part 1). */
  guildId: string;
  /** Discord user ID (composite PK part 2). */
  userId: string;
  /** Total XP earned in this guild. */
  xp: number;
  /** Computed level from XP. */
  level: number;
  /** Active warning count. */
  warnings: number;
  /** Coin balance. */
  coins: number;
  /** Consecutive daily claim streak. */
  dailyStreak: number;
  /** ISO 8601 timestamp of last daily reset. */
  lastDailyReset: string | null;
  /** ISO 8601 timestamp of last daily claim. */
  lastDaily: string | null;
  /** ISO 8601 timestamp of last XP gain. */
  lastXpGain: string | null;
}

// ── Ticket ───────────────────────────────────────────────────────────────

export type TicketStatus = "open" | "claimed" | "closed";

export interface Ticket {
  /** UUID primary key. */
  id: string;
  /** Sequential ticket number per guild. */
  ticketNumber: number;
  /** Discord guild ID. */
  guildId: string;
  /** Discord user ID of the ticket author. */
  authorId: string;
  /** Discord channel ID of the ticket thread/channel. */
  channelId: string;
  /** Current ticket status. */
  status: TicketStatus;
  /** ISO 8601 timestamp of ticket creation. */
  createdAt: string;
  /** ISO 8601 timestamp of last activity. */
  lastActivity: string;
  /** Ticket category UUID (FK → ticket_category.id). */
  categoryId: string | null;
  /** Discord user ID of the staff member who claimed the ticket. */
  claimedBy: string | null;
  /** URL to the HTML transcript. */
  transcriptUrl: string | null;
  /** ISO 8601 timestamp when the ticket was closed. */
  closedAt: string | null;
}

// ── Ticket Category ──────────────────────────────────────────────────────

export interface TicketCategory {
  /** UUID primary key. */
  id: string;
  /** Discord guild ID. */
  guildId: string;
  /** Display name for this category. */
  name: string;
  /** Optional emoji for the dropdown button. */
  emoji: string | null;
  /** Description shown in the ticket panel. */
  description: string | null;
  /** Display order in the dropdown. */
  position: number;
  /** Whether the category is active. */
  active: boolean;
  /** ISO 8601 timestamp of creation. */
  createdAt: string | null;
}

// ── Infraction ───────────────────────────────────────────────────────────

export type InfractionType = "WARN" | "MUTE" | "KICK" | "BAN";

export interface Infraction {
  /** UUID primary key. */
  id: string;
  /** Discord guild ID. */
  guildId: string;
  /** Discord user ID of the punished member. */
  targetId: string;
  /** Discord user ID of the moderator who issued the infraction. */
  moderatorId: string;
  /** Infraction type. */
  type: InfractionType;
  /** Human-readable reason. */
  reason: string;
  /** ISO 8601 timestamp when the infraction was issued. */
  createdAt: string;
  /** Whether the infraction is still active (not pardoned/expired). */
  active: boolean;
  /** ISO 8601 timestamp when the infraction expires (null = permanent). */
  expiresAt: string | null;
}

// ── Discord API ──────────────────────────────────────────────────────────

export interface DiscordGuild {
  /** Discord guild ID. */
  id: string;
  /** Guild name. */
  name: string;
  /** Icon hash (null if no custom icon). */
  icon: string | null;
  /** Whether the current user owns this guild. */
  owner: boolean;
  /** Permission bitfield for the current user (string-encoded integer). */
  permissions: string;
}

// ── Action Results ───────────────────────────────────────────────────────

export type ActionResult =
  | { success: true; message: string }
  | { success: false; error: string; field?: string };
