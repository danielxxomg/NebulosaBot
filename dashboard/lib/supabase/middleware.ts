import { createServerClient } from "@supabase/ssr";
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

/**
 * Read a required public env var, throwing at first use when unset so a
 * misconfigured deployment fails loudly instead of silently issuing
 * requests to an undefined URL.
 */
function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

/**
 * Updates the Supabase session in middleware context.
 *
 * Must be called in every middleware invocation to refresh the auth cookie
 * and make the session available for downstream Server Components.
 *
 * Uses the `getAll`/`setAll` cookie API required by @supabase/ssr in
 * Next.js middleware (creates cookies on the request AND response).
 *
 * @returns supabaseResponse (with refreshed cookies) and the current session.
 */
export const updateSession = async (request: NextRequest) => {
  let supabaseResponse = NextResponse.next({ request });

  const supabase = createServerClient(
    requireEnv("NEXT_PUBLIC_SUPABASE_URL"),
    requireEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY"),
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(
          cookiesToSet: { name: string; value: string; options?: Record<string, unknown> }[]
        ) {
          for (const { name, value } of cookiesToSet) {
            request.cookies.set(name, value);
          }
          supabaseResponse = NextResponse.next({ request });
          for (const { name, value, options } of cookiesToSet) {
            supabaseResponse.cookies.set(name, value, options as never);
          }
        },
      },
    }
  );

  const {
    data: { session },
  } = await supabase.auth.getSession();

  return { session, supabase, supabaseResponse };
};
