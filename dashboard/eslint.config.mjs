/** ESLint flat config — non-interactive replacement for the deprecated `next lint` prompt.
 *
 * `npm run lint` is overridden (in package.json) to `eslint .` so CI/verify never
 * enters the interactive ESLint setup prompt that `next lint` shows when no legacy
 * `.eslintrc` is present. This flat config loads the Next.js shared config via
 * `@eslint/eslintrc` FlatCompat so no legacy file is required.
 */
import { FlatCompat } from "@eslint/eslintrc";
import { fileURLToPath } from "url";
import { dirname } from "path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const compat = new FlatCompat({ baseDirectory: __dirname });

const config = [
  {
    ignores: [".next/**", "node_modules/**", "next-env.d.ts"],
  },
  ...compat.extends("next/core-web-vitals"),
];

export default config;
