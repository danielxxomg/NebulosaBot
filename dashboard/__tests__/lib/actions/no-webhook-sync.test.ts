import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

/**
 * cache-sync-realtime PR 2 — architectural boundary guard.
 *
 * The inbound webhook (Cloudflare Tunnel + HMAC) was replaced by the outbound
 * Supabase Realtime CDC subscriber.  Dashboard Server Actions MUST NOT depend
 * on `@/lib/webhook-sync` / `notifyWebhookSync` anymore — leaving the import
 * in place would either break (once the module is deleted) or silently
 * re-couple the dashboard to a removed capability.
 *
 * This guard reads the action source files and asserts the dependency is gone,
 * preventing accidental re-introduction.
 */

const ACTIONS_DIR = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../../lib/actions"
);

const ACTION_FILES = [
  "guild-actions.ts",
  "greeting-actions.ts",
  "economy-actions.ts",
] as const;

describe("cache-sync-realtime PR 2: actions do not depend on webhook-sync", () => {
  for (const file of ACTION_FILES) {
    it(`${file} does not import or call webhook-sync / notifyWebhookSync`, () => {
      const source = readFileSync(path.resolve(ACTIONS_DIR, file), "utf8");
      expect(source).not.toContain("webhook-sync");
      expect(source).not.toContain("notifyWebhookSync");
    });
  }
});
