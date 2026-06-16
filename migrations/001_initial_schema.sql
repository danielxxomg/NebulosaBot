-- ============================================================================
-- Migration 001: Initial Schema
-- NebulosaBot — Core Foundation Tables
-- ============================================================================
-- Run this against your Supabase SQL editor or via `supabase db push`.
-- FK dependency order: Guild → User → Member → Infraction → Ticket
-- Rollback: DROP TABLE in reverse order (Ticket → Infraction → Member → User → Guild).

-- ----------------------------------------------------------------------------
-- Guild
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS guild (
    id              TEXT PRIMARY KEY,          -- Discord guild/snowflake ID
    prefix          TEXT NOT NULL DEFAULT 'nb!',
    language        TEXT NOT NULL DEFAULT 'es',
    "modRoleId"     TEXT,                      -- NULL = no mod role configured
    "logChannelId"  TEXT,                      -- NULL = logging disabled
    "ticketCategoryId" TEXT,                   -- NULL = no ticket category
    "logEnabled"    BOOLEAN NOT NULL DEFAULT FALSE,
    "welcomeEnabled" BOOLEAN NOT NULL DEFAULT FALSE,
    active          BOOLEAN NOT NULL DEFAULT TRUE
);

-- ----------------------------------------------------------------------------
-- User
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "user" (
    id          TEXT PRIMARY KEY,              -- Discord user/snowflake ID
    username    TEXT NOT NULL,
    "avatarUrl" TEXT,                          -- NULL = default avatar
    "lastSeen"  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- Member  (composite PK: guildId + userId)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS member (
    "guildId"     TEXT NOT NULL REFERENCES guild(id) ON DELETE CASCADE,
    "userId"      TEXT NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    xp            BIGINT NOT NULL DEFAULT 0,
    level         INTEGER NOT NULL DEFAULT 0,
    warnings      INTEGER NOT NULL DEFAULT 0,
    coins         BIGINT NOT NULL DEFAULT 0,
    "lastDaily"   TIMESTAMPTZ,                 -- NULL = never claimed
    "lastXpGain"  TIMESTAMPTZ,                 -- NULL = never gained
    PRIMARY KEY ("guildId", "userId")
);

-- ----------------------------------------------------------------------------
-- Infraction
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS infraction (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    "guildId"       TEXT NOT NULL REFERENCES guild(id) ON DELETE CASCADE,
    "targetId"      TEXT NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    "moderatorId"   TEXT NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    type            TEXT NOT NULL CHECK (type IN ('WARN', 'MUTE', 'KICK', 'BAN')),
    reason          TEXT NOT NULL,
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    "expiresAt"     TIMESTAMPTZ,               -- NULL = permanent (for WARN/KICK/BAN)
    "createdAt"     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- Ticket
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ticket (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    "ticketNumber"  INTEGER NOT NULL,          -- Sequential per guild (app-maintained)
    "guildId"       TEXT NOT NULL REFERENCES guild(id) ON DELETE CASCADE,
    "authorId"      TEXT NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    "channelId"     TEXT NOT NULL,             -- Discord channel snowflake
    "categoryId"    TEXT,                      -- NULL = no category
    status          TEXT NOT NULL DEFAULT 'open'
                    CHECK (status IN ('open', 'claimed', 'closed')),
    "claimedBy"     TEXT,                      -- NULL = unclaimed
    "transcriptUrl" TEXT,                      -- NULL = no transcript yet
    "createdAt"     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    "closedAt"      TIMESTAMPTZ,               -- NULL = still open
    "lastActivity"  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- Indexes (optional but recommended for Phase 2+)
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_member_guild ON member ("guildId");
CREATE INDEX IF NOT EXISTS idx_infraction_guild_target ON infraction ("guildId", "targetId");
CREATE INDEX IF NOT EXISTS idx_ticket_guild_status ON ticket ("guildId", status);
CREATE INDEX IF NOT EXISTS idx_ticket_guild_number ON ticket ("guildId", "ticketNumber");
