import { defineConfig } from "oxlint";

// Ultracite core preset over native Oxlint Rust rules.
// Advisory phase: findings are triaged in the future dashboard-QA SDD
// before any gate goes blocking (see .github/workflows/code-quality.yml).
import core from "ultracite/oxlint/core";

export default defineConfig({
  extends: [core],
  ignorePatterns: core.ignorePatterns,

  // Scoped severities (2026-08-23): test ergonomics vs production signal.
  // In __tests__, `async` callbacks without await and non-null assertions
  // are idiomatic; in lib/app they stay errors (real bug surface).
  overrides: [
    {
      files: ["**/__tests__/**"],
      rules: {
        "require-await": "warn",
        "typescript/no-non-null-assertion": "warn",
      },
    },
  ],

  // ── Commented out: NOT confident yet — revisit in dashboard-QA SDD ──
  // Type-aware linting requires tsgolint (separate binary, experimental):
  // import { defineConfig as tsgo } from ... — see oxc-project/tsgolint docs.
  //
  // Framework preset layer (react/next categories live in core already per
  // Ultracite v7; explicit opt-in only if we adopt js-plugins later):
  // extends: [core, jsPlugins] + npm i -D eslint-plugin-github eslint-plugin-sonarjs oxlint-plugin-react-doctor
});
