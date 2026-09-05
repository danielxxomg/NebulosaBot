import { createBrowserClient, createServerClient } from '@supabase/ssr';
import type { CookieOptions } from '@supabase/ssr';
import { cookies } from "next/headers";

/**
 * Read a required public env var, throwing at first use when unset so a
 * misconfigured deployment fails loudly instead of silently issuing
 * requests to an undefined URL.
 */
const requireEnv = (name: string): string => {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
};

/**
 * Create a browser-side Supabase client using the anon public key.
 *
 * Used in Client Components for real-time subscriptions and
 * client-side data fetching from the browser.
 */
export const createClient = () =>
  createBrowserClient(
    requireEnv("NEXT_PUBLIC_SUPABASE_URL"),
    requireEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
  );

/**
 * Create a server-side Supabase client using cookie-based auth.
 *
 * Used in Server Components, Server Actions, and Route Handlers.
 * Automatically reads/writes the auth session cookie via `next/headers`.
 */
export const createServerSupabaseClient = async () => {
  const cookieStore = await cookies();

  return createServerClient(
    requireEnv("NEXT_PUBLIC_SUPABASE_URL"),
    requireEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY"),
    {
      cookies: {
        get(name: string) {
          return cookieStore.get(name)?.value;
        },
        async remove(name: string, options: CookieOptions) {
          try {
            await cookieStore.set({ name, value: "", ...options });
          } catch {
            // Cookie can only be modified in a Server Action or Route Handler.
          }
        },
        async set(name: string, value: string, options: CookieOptions) {
          try {
            await cookieStore.set({ name, value, ...options });
          } catch {
            // Cookie can only be modified in a Server Action or Route Handler.
          }
        },
      },
    }
  );
};

/**
 * Create a server-side Supabase client using the service role key.
 *
 * Bypasses Row Level Security. Use ONLY in trusted server contexts
 * (Server Components, Server Actions) — NEVER expose to the browser.
 */
export const createServiceClient = async () => {
  const cookieStore = await cookies();

  return createServerClient(
    requireEnv("NEXT_PUBLIC_SUPABASE_URL"),
    requireEnv("SUPABASE_SERVICE_ROLE_KEY"),
    {
      cookies: {
        get(name: string) {
          return cookieStore.get(name)?.value;
        },
        async remove(name: string, options: CookieOptions) {
          try {
            await cookieStore.set({ name, value: "", ...options });
          } catch {
            // Cookie can only be modified in a Server Action or Route Handler.
          }
        },
        async set(name: string, value: string, options: CookieOptions) {
          try {
            await cookieStore.set({ name, value, ...options });
          } catch {
            // Cookie can only be modified in a Server Action or Route Handler.
          }
        },
      },
    }
  );
};
