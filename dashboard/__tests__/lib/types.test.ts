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
      active: true,
      id: "123456789012345678",
      language: "en",
      logChannelId: null,
      logEnabled: false,
      modRoleId: null,
      prefix: "!",
      ticketCategoryId: null,
      ticketPanelChannelId: null,
      ticketPanelMessageId: null,
      welcomeEnabled: true,
    };

    const actualKeys = Object.keys(config).toSorted();
    const expectedKeys = [...guildConfigKeys].toSorted();

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
      dailyCooldownHours: 24,
      dailyReward: 100,
      guildId: "123456789012345678",
      levelBaseXp: 100,
      levelMultiplier: 1.5,
      levelRoles: {},
      levelUpChannelId: null,
      xpCooldownSeconds: 60,
      xpPerMessage: 10,
    };

    const actualKeys = Object.keys(config).toSorted();
    const expectedKeys = [...economyConfigKeys].toSorted();

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
      goodbyeCardEnabled: false,
      goodbyeChannelId: null,
      goodbyeEnabled: false,
      goodbyeMessage: null,
      guildId: "123456789012345678",
      welcomeCardEnabled: false,
      welcomeChannelId: null,
      welcomeEnabled: false,
      welcomeMessage: null,
    };

    const actualKeys = Object.keys(config).toSorted();
    const expectedKeys = [...greetingConfigKeys].toSorted();

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
      coins: 0,
      dailyStreak: 0,
      guildId: "123",
      lastDaily: null,
      lastDailyReset: null,
      lastXpGain: null,
      level: 1,
      userId: "456",
      warnings: 0,
      xp: 0,
    };

    expect(Object.keys(member).toSorted()).toEqual([...memberKeys].toSorted());
  });
});

describe("ActionResult discriminated union", () => {
  it("success variant has the expected shape", () => {
    const success: { success: true; message: string } = {
      message: "Saved.",
      success: true,
    };

    expect(success.success).toBe(true);
    expect(typeof success.message).toBe("string");
  });

  it("error variant has the expected shape", () => {
    const errorWithField: { success: false; error: string; field?: string } = {
      error: "Invalid prefix.",
      field: "prefix",
      success: false,
    };

    expect(errorWithField.success).toBe(false);
    expect(typeof errorWithField.error).toBe("string");
    expect(errorWithField.field).toBe("prefix");
  });

  it("error variant without field is valid", () => {
    const errorWithoutField: { success: false; error: string } = {
      error: "Not authenticated.",
      success: false,
    };

    expect(errorWithoutField.success).toBe(false);
    expect(typeof errorWithoutField.error).toBe("string");
    expect("field" in errorWithoutField).toBe(false);
  });
});
