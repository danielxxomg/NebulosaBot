import { describe, it, expect } from "vitest";
import { resolveConfig, loadConfigFromFile } from "vite";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";

describe("Vitest environment loading boundary", () => {
  it("vitest.config.ts explicitly sets envDir: false", async () => {
    const configPath = path.resolve(__dirname, "../vitest.config.ts");
    const loaded = await loadConfigFromFile(
      { command: "serve", mode: "test" },
      configPath
    );
    expect(loaded).toBeDefined();
    expect(loaded?.config?.envDir).toBe(false);
  });

  it("Vite config resolution ignores .env and .env.local when envDir is false", async () => {
    const fixtureDir = fs.mkdtempSync(
      path.join(os.tmpdir(), "vitest-env-boundary-")
    );
    try {
      // Create a canary .env.local in fixture directory
      fs.writeFileSync(
        path.join(fixtureDir, ".env.local"),
        "VITE_CANARY_BOUNDARY_LEAK=leak_detected\nCANARY_SECRET=secret\n"
      );

      // Resolve with envDir: false (our required security boundary)
      const safeConfig = await resolveConfig(
        { root: fixtureDir, envDir: false },
        "serve",
        "test"
      );
      expect(safeConfig.envDir).toBe(false);
      expect(safeConfig.env.VITE_CANARY_BOUNDARY_LEAK).toBeUndefined();

      // For comparison, verify that default Vite behavior WOULD load the canary
      const leakyConfig = await resolveConfig(
        { root: fixtureDir },
        "serve",
        "test"
      );
      expect(leakyConfig.env.VITE_CANARY_BOUNDARY_LEAK).toBe("leak_detected");
    } finally {
      fs.rmSync(fixtureDir, { recursive: true, force: true });
    }
  });

  it("resolved project vitest config has envDir: false", async () => {
    const configPath = path.resolve(__dirname, "../vitest.config.ts");
    const resolved = await resolveConfig(
      { configFile: configPath },
      "serve",
      "test"
    );
    expect(resolved.envDir).toBe(false);
  });
});
