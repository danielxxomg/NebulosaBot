import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// ---------------------------------------------------------------------------
// hasAdministratorPerm — pure function, no mocking needed
// ---------------------------------------------------------------------------

describe("hasAdministratorPerm", () => {
  // We import dynamically so the module-level fetch call inside discord.ts
  // doesn't execute until we've set up mocks for the fetchUserGuilds tests.
  let hasAdministratorPerm: (permissions: string) => boolean;

  beforeAll(async () => {
    const mod = await import("@/lib/discord");
    hasAdministratorPerm = mod.hasAdministratorPerm;
  });

  it("returns true when ADMINISTRATOR bit (0x8) is set", () => {
    expect(hasAdministratorPerm("8")).toBe(true);
  });

  it("returns true when permission bitfield includes 8 plus other bits", () => {
    // 8 (ADMIN) + 1024 (VIEW_CHANNEL) = 1032
    expect(hasAdministratorPerm("1032")).toBe(true);
  });

  it("returns false when ADMINISTRATOR bit is absent", () => {
    expect(hasAdministratorPerm("1024")).toBe(false);
  });

  it("returns false for 0", () => {
    expect(hasAdministratorPerm("0")).toBe(false);
  });

  it("returns false for empty string", () => {
    expect(hasAdministratorPerm("")).toBe(false);
  });

  it("correctly handles large bitfields (BigInt) — has admin", () => {
    // 0x2000000000F = 2199023255567 — last nibble is F (1111), includes 0x8
    const bigPerm = "2199023255567";
    expect(hasAdministratorPerm(bigPerm)).toBe(true);
  });

  it("correctly identifies non-admin in large bitfields", () => {
    // 0x20000000007 = 2199023255559 — last nibble is 7 (0111), no 0x8 bit
    const bigPerm = "2199023255559";
    expect(hasAdministratorPerm(bigPerm)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// fetchUserGuilds — requires mocking the global fetch
// ---------------------------------------------------------------------------

describe("fetchUserGuilds", () => {
  let fetchUserGuilds: (token: string) => Promise<unknown[]>;

  beforeAll(async () => {
    // Clear the in-memory cache between test runs by re-importing.
    vi.resetModules();
    const mod = await import("@/lib/discord");
    fetchUserGuilds = mod.fetchUserGuilds;
  });

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns guilds when the Discord API responds successfully", async () => {
    const mockGuilds = [
      {
        id: "123456789012345678",
        name: "Test Guild",
        icon: "abc123",
        owner: true,
        permissions: "8",
      },
      {
        id: "987654321098765432",
        name: "Other Guild",
        icon: null,
        owner: false,
        permissions: "1024",
      },
    ];

    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(mockGuilds), { status: 200 })
    );

    const result = await fetchUserGuilds("fake-access-token-1234567890abcdef");
    expect(result).toEqual(mockGuilds);
  });

  it("throws when Discord API returns a non-200 status", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response("Unauthorized", { status: 401, statusText: "Unauthorized" })
    );

    await expect(
      fetchUserGuilds("invalid-token")
    ).rejects.toThrow("Discord API error: 401 Unauthorized");
  });

  it("caches results so a second call does not hit the network", async () => {
    const mockGuilds = [{ id: "111", name: "Cached", icon: null, owner: true, permissions: "8" }];
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(JSON.stringify(mockGuilds), { status: 200 })
      );

    // Re-import to ensure clean cache.
    vi.resetModules();
    const fresh = await import("@/lib/discord");
    const fn = fresh.fetchUserGuilds;

    // First call — hits network.
    await fn("token-abc");
    expect(fetchSpy).toHaveBeenCalledTimes(1);

    // Second call — should be cached.
    await fn("token-abc");
    expect(fetchSpy).toHaveBeenCalledTimes(1); // Still 1 — cached!
  });
});
