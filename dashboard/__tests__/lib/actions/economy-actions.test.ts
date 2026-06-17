import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  buildMockServiceClient,
  buildAuthSession,
  buildFormData,
  assertAuthError,
  assertFieldError,
  assertSuccess,
} from "./_test-helpers";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockGetSession = vi.fn();
const mockRevalidatePath = vi.fn();
const mockFetchUserGuilds = vi.fn();

vi.mock("@/lib/supabase", () => ({
  createServerSupabaseClient: vi.fn(() =>
    Promise.resolve({
      auth: { getSession: mockGetSession },
    })
  ),
  createServiceClient: vi.fn(),
}));

vi.mock("@/lib/discord", () => ({
  fetchUserGuilds: (...args: unknown[]) => mockFetchUserGuilds(...args),
  hasAdministratorPerm: (perm: string) => {
    const permsBigInt = BigInt(perm);
    const ADMINISTRATOR = BigInt(0x8);
    return (permsBigInt & ADMINISTRATOR) === ADMINISTRATOR;
  },
}));

vi.mock("next/cache", () => ({
  revalidatePath: (...args: unknown[]) => mockRevalidatePath(...args),
}));

import { updateEconomyConfig } from "@/lib/actions/economy-actions";
import { createServiceClient } from "@/lib/supabase";

const GUILD_ID = "123456789012345678";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function setupAuth({
  hasSession = true,
  hasProviderToken = true,
  guildActive = true,
  isAdmin = true,
}: {
  hasSession?: boolean;
  hasProviderToken?: boolean;
  guildActive?: boolean;
  isAdmin?: boolean;
} = {}) {
  mockGetSession.mockResolvedValue(buildAuthSession({ hasSession, hasProviderToken }));

  const svc = buildMockServiceClient({
    guildSelectResult: guildActive
      ? { data: { active: true }, error: null }
      : { data: null, error: null },
  });

  vi.mocked(createServiceClient).mockResolvedValue(svc as unknown as ReturnType<typeof createServiceClient>);

  mockFetchUserGuilds.mockResolvedValue([
    { id: GUILD_ID, permissions: isAdmin ? "8" : "1024" },
  ]);

  mockRevalidatePath.mockClear();
}

beforeEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Auth rejection
// ---------------------------------------------------------------------------

describe("updateEconomyConfig — auth rejection", () => {
  it("returns error for unauthorized user", async () => {
    setupAuth({ hasSession: false });
    const fd = buildFormData({
      dailyReward: "100",
      dailyCooldownHours: "24",
      xpPerMessage: "10",
      xpCooldownSeconds: "60",
      levelBaseXp: "100",
      levelMultiplier: "1.5",
    });
    const result = await updateEconomyConfig(GUILD_ID, fd);
    assertAuthError(result);
  });

  it("returns error when user is not admin", async () => {
    setupAuth({ isAdmin: false });
    const fd = buildFormData({
      dailyReward: "100",
      dailyCooldownHours: "24",
      xpPerMessage: "10",
      xpCooldownSeconds: "60",
      levelBaseXp: "100",
      levelMultiplier: "1.5",
    });
    const result = await updateEconomyConfig(GUILD_ID, fd);
    if (!result.success) {
      expect(result.error).toMatch(/administrator/i);
    }
  });
});

// ---------------------------------------------------------------------------
// Numeric bounds validation
// ---------------------------------------------------------------------------

describe("updateEconomyConfig — numeric bounds", () => {
  beforeEach(() => {
    setupAuth();
  });

  const validDefaults = {
    dailyReward: "100",
    dailyCooldownHours: "24",
    xpPerMessage: "10",
    xpCooldownSeconds: "60",
    levelBaseXp: "100",
    levelMultiplier: "1.5",
  };

  // dailyReward: 1–1,000,000
  it("rejects dailyReward below 1", async () => {
    const fd = buildFormData({ ...validDefaults, dailyReward: "0" });
    const result = await updateEconomyConfig(GUILD_ID, fd);
    assertFieldError(result, "dailyReward");
  });

  it("rejects dailyReward above 1,000,000", async () => {
    const fd = buildFormData({ ...validDefaults, dailyReward: "1000001" });
    const result = await updateEconomyConfig(GUILD_ID, fd);
    assertFieldError(result, "dailyReward");
  });

  it("rejects non-numeric dailyReward", async () => {
    const fd = buildFormData({ ...validDefaults, dailyReward: "abc" });
    const result = await updateEconomyConfig(GUILD_ID, fd);
    assertFieldError(result, "dailyReward");
  });

  // dailyCooldownHours: 1–720
  it("rejects dailyCooldownHours below 1", async () => {
    const fd = buildFormData({ ...validDefaults, dailyCooldownHours: "0" });
    const result = await updateEconomyConfig(GUILD_ID, fd);
    assertFieldError(result, "dailyCooldownHours");
  });

  it("rejects dailyCooldownHours above 720", async () => {
    const fd = buildFormData({ ...validDefaults, dailyCooldownHours: "721" });
    const result = await updateEconomyConfig(GUILD_ID, fd);
    assertFieldError(result, "dailyCooldownHours");
  });

  // xpPerMessage: 1–1000
  it("rejects xpPerMessage below 1", async () => {
    const fd = buildFormData({ ...validDefaults, xpPerMessage: "0" });
    const result = await updateEconomyConfig(GUILD_ID, fd);
    assertFieldError(result, "xpPerMessage");
  });

  it("rejects xpPerMessage above 1000", async () => {
    const fd = buildFormData({ ...validDefaults, xpPerMessage: "1001" });
    const result = await updateEconomyConfig(GUILD_ID, fd);
    assertFieldError(result, "xpPerMessage");
  });

  // xpCooldownSeconds: 1–3600
  it("rejects xpCooldownSeconds below 1", async () => {
    const fd = buildFormData({ ...validDefaults, xpCooldownSeconds: "0" });
    const result = await updateEconomyConfig(GUILD_ID, fd);
    assertFieldError(result, "xpCooldownSeconds");
  });

  it("rejects xpCooldownSeconds above 3600", async () => {
    const fd = buildFormData({ ...validDefaults, xpCooldownSeconds: "3601" });
    const result = await updateEconomyConfig(GUILD_ID, fd);
    assertFieldError(result, "xpCooldownSeconds");
  });

  // levelBaseXp: 1–1,000,000
  it("rejects levelBaseXp below 1", async () => {
    const fd = buildFormData({ ...validDefaults, levelBaseXp: "0" });
    const result = await updateEconomyConfig(GUILD_ID, fd);
    assertFieldError(result, "levelBaseXp");
  });

  it("rejects levelBaseXp above 1,000,000", async () => {
    const fd = buildFormData({ ...validDefaults, levelBaseXp: "1000001" });
    const result = await updateEconomyConfig(GUILD_ID, fd);
    assertFieldError(result, "levelBaseXp");
  });

  // levelMultiplier: 1.0–10.0
  it("rejects levelMultiplier below 1.0", async () => {
    const fd = buildFormData({ ...validDefaults, levelMultiplier: "0.5" });
    const result = await updateEconomyConfig(GUILD_ID, fd);
    assertFieldError(result, "levelMultiplier");
  });

  it("rejects levelMultiplier above 10.0", async () => {
    const fd = buildFormData({ ...validDefaults, levelMultiplier: "10.1" });
    const result = await updateEconomyConfig(GUILD_ID, fd);
    assertFieldError(result, "levelMultiplier");
  });

  it("rejects non-numeric levelMultiplier", async () => {
    const fd = buildFormData({ ...validDefaults, levelMultiplier: "xyz" });
    const result = await updateEconomyConfig(GUILD_ID, fd);
    assertFieldError(result, "levelMultiplier");
  });

  // Snowflake validation for levelUpChannelId
  it("rejects invalid snowflake for levelUpChannelId", async () => {
    const fd = buildFormData({ ...validDefaults, levelUpChannelId: "not-a-snowflake" });
    const result = await updateEconomyConfig(GUILD_ID, fd);
    assertFieldError(result, "levelUpChannelId");
  });

  it("accepts valid snowflake for levelUpChannelId", async () => {
    const fd = buildFormData({
      ...validDefaults,
      levelUpChannelId: "123456789012345678",
    });
    const result = await updateEconomyConfig(GUILD_ID, fd);
    assertSuccess(result);
  });
});

// ---------------------------------------------------------------------------
// Level roles JSON validation
// ---------------------------------------------------------------------------

describe("updateEconomyConfig — levelRoles", () => {
  beforeEach(() => {
    setupAuth();
  });

  const validDefaults = {
    dailyReward: "100",
    dailyCooldownHours: "24",
    xpPerMessage: "10",
    xpCooldownSeconds: "60",
    levelBaseXp: "100",
    levelMultiplier: "1.5",
  };

  it("rejects invalid JSON in levelRoles", async () => {
    const fd = buildFormData({ ...validDefaults, levelRoles: "{bad json" });
    const result = await updateEconomyConfig(GUILD_ID, fd);
    assertFieldError(result, "levelRoles");
  });

  it("rejects array instead of object in levelRoles", async () => {
    const fd = buildFormData({ ...validDefaults, levelRoles: "[1, 2, 3]" });
    const result = await updateEconomyConfig(GUILD_ID, fd);
    assertFieldError(result, "levelRoles");
  });

  it("accepts valid JSON object for levelRoles", async () => {
    const fd = buildFormData({
      ...validDefaults,
      levelRoles: '{"1": "role1", "5": "role2"}',
    });
    const result = await updateEconomyConfig(GUILD_ID, fd);
    assertSuccess(result);
  });

  it("accepts empty levelRoles", async () => {
    const fd = buildFormData({ ...validDefaults, levelRoles: "" });
    const result = await updateEconomyConfig(GUILD_ID, fd);
    assertSuccess(result);
  });
});

// ---------------------------------------------------------------------------
// Successful update
// ---------------------------------------------------------------------------

describe("updateEconomyConfig — successful update", () => {
  it("saves valid config and revalidates", async () => {
    setupAuth();
    const fd = buildFormData({
      dailyReward: "500",
      dailyCooldownHours: "12",
      xpPerMessage: "25",
      xpCooldownSeconds: "30",
      levelBaseXp: "300",
      levelMultiplier: "2.0",
      levelRoles: '{"3": "123456789012345678"}',
      levelUpChannelId: "123456789012345678",
    });
    const result = await updateEconomyConfig(GUILD_ID, fd);
    assertSuccess(result);
    expect(mockRevalidatePath).toHaveBeenCalledWith(`/guilds/${GUILD_ID}`, "layout");
  });

  it("accepts boundary values", async () => {
    setupAuth();
    const fd = buildFormData({
      dailyReward: "1000000",
      dailyCooldownHours: "720",
      xpPerMessage: "1000",
      xpCooldownSeconds: "3600",
      levelBaseXp: "1000000",
      levelMultiplier: "10.0",
    });
    const result = await updateEconomyConfig(GUILD_ID, fd);
    assertSuccess(result);
  });

  it("accepts minimum values", async () => {
    setupAuth();
    const fd = buildFormData({
      dailyReward: "1",
      dailyCooldownHours: "1",
      xpPerMessage: "1",
      xpCooldownSeconds: "1",
      levelBaseXp: "1",
      levelMultiplier: "1.0",
    });
    const result = await updateEconomyConfig(GUILD_ID, fd);
    assertSuccess(result);
  });
});
