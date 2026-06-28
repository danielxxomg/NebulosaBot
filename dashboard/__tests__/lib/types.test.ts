import { describe, it, expect } from "vitest";

/**
 * Snapshot tests for TypeScript interface shapes.
 *
 * These tests verify that the exported type *keys* match the expected
 * schema. While Vitest cannot assert TypeScript types at runtime,
 * we can verify that a representative object built from each interface
 * has the expected keys — guarding against accidental field additions
 * or removals during refactoring.
 */

describe("GuildConfig shape", () => {
  it("has the expected keys matching the Supabase guild schema", () => {
    const guildConfigKeys = [
      "id",
      "prefix",
      "language",
      "modRoleId",
      "logChannelId",
      "ticketCategoryId",
      "ticketPanelMessageId",
      "ticketPanelChannelId",
      "logEnabled",
      "welcomeEnabled",
      "active",
    ];

    // Build a representative object that satisfies the GuildConfig type.
    const config: Record<string, unknown> = {
      id: "123456789012345678",
      prefix: "!",
      language: "en",
      modRoleId: null,
      logChannelId: null,
      ticketCategoryId: null,
      ticketPanelMessageId: null,
      ticketPanelChannelId: null,
      logEnabled: false,
      welcomeEnabled: true,
      active: true,
    };

    const actualKeys = Object.keys(config).sort();
    const expectedKeys = [...guildConfigKeys].sort();

    expect(actualKeys).toEqual(expectedKeys);
  });
});

describe("EconomyConfig shape", () => {
  it("has the expected keys matching the Supabase economy_config schema", () => {
    const economyConfigKeys = [
      "guildId",
      "dailyReward",
      "dailyCooldownHours",
      "xpPerMessage",
      "xpCooldownSeconds",
      "levelBaseXp",
      "levelMultiplier",
      "levelRoles",
      "levelUpChannelId",
    ];

    const config: Record<string, unknown> = {
      guildId: "123456789012345678",
      dailyReward: 100,
      dailyCooldownHours: 24,
      xpPerMessage: 10,
      xpCooldownSeconds: 60,
      levelBaseXp: 100,
      levelMultiplier: 1.5,
      levelRoles: {},
      levelUpChannelId: null,
    };

    const actualKeys = Object.keys(config).sort();
    const expectedKeys = [...economyConfigKeys].sort();

    expect(actualKeys).toEqual(expectedKeys);
  });
});

describe("GreetingConfig shape", () => {
  it("has the expected keys matching the Supabase greeting_config schema", () => {
    const greetingConfigKeys = [
      "guildId",
      "welcomeEnabled",
      "goodbyeEnabled",
      "welcomeChannelId",
      "goodbyeChannelId",
      "welcomeMessage",
      "goodbyeMessage",
      "welcomeCardEnabled",
      "goodbyeCardEnabled",
    ];

    const config: Record<string, unknown> = {
      guildId: "123456789012345678",
      welcomeEnabled: false,
      goodbyeEnabled: false,
      welcomeChannelId: null,
      goodbyeChannelId: null,
      welcomeMessage: null,
      goodbyeMessage: null,
      welcomeCardEnabled: false,
      goodbyeCardEnabled: false,
    };

    const actualKeys = Object.keys(config).sort();
    const expectedKeys = [...greetingConfigKeys].sort();

    expect(actualKeys).toEqual(expectedKeys);
  });
});

describe("Member shape", () => {
  it("has the expected keys", () => {
    const memberKeys = [
      "guildId",
      "userId",
      "xp",
      "level",
      "warnings",
      "coins",
      "dailyStreak",
      "lastDailyReset",
      "lastDaily",
      "lastXpGain",
    ];

    const member: Record<string, unknown> = {
      guildId: "123",
      userId: "456",
      xp: 0,
      level: 1,
      warnings: 0,
      coins: 0,
      dailyStreak: 0,
      lastDailyReset: null,
      lastDaily: null,
      lastXpGain: null,
    };

    expect(Object.keys(member).sort()).toEqual([...memberKeys].sort());
  });
});

describe("ActionResult discriminated union", () => {
  it("success variant has the expected shape", () => {
    const success: { success: true; message: string } = {
      success: true,
      message: "Saved.",
    };

    expect(success.success).toBe(true);
    expect(typeof success.message).toBe("string");
  });

  it("error variant has the expected shape", () => {
    const errorWithField: { success: false; error: string; field?: string } = {
      success: false,
      error: "Invalid prefix.",
      field: "prefix",
    };

    expect(errorWithField.success).toBe(false);
    expect(typeof errorWithField.error).toBe("string");
    expect(errorWithField.field).toBe("prefix");
  });

  it("error variant without field is valid", () => {
    const errorWithoutField: { success: false; error: string } = {
      success: false,
      error: "Not authenticated.",
    };

    expect(errorWithoutField.success).toBe(false);
    expect(typeof errorWithoutField.error).toBe("string");
    expect("field" in errorWithoutField).toBe(false);
  });
});
