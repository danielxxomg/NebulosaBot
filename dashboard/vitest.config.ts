import { defineConfig } from "vitest/config";
import path from "path";

export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: [],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
  // The project's tsconfig sets `jsx: "preserve"` (required by Next.js/SWC),
  // which Vite/oxc respects and therefore skips JSX transformation — breaking
  // component render tests. Override only for the test pipeline (oxc is the
  // active transformer in rolldown-vite; `esbuild` options are ignored) so
  // Next.js (which uses SWC, not tsc/Vite, for its own JSX) is unaffected.
  oxc: {
    // Object form (JsxOptions) — the string "react-jsx" is runtime-valid but
    // rejected by Vite's types, which breaks `next build` type-checking.
    jsx: { runtime: "automatic" },
  },
});
