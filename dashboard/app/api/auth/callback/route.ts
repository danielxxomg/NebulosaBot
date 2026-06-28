import { createServerSupabaseClient } from "@/lib/supabase";
import { NextResponse } from "next/server";

/**
 * Discord OAuth2 callback handler.
 *
 * Discord redirects here after the user authorizes the application.
 * Supabase exchanges the OAuth2 authorization `code` for a session
 * cookie, then redirects the browser to the original target page.
 *
 * GET /api/auth/callback?code={code}&next={path}
 */
export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  const next = searchParams.get("next") ?? "/";

  if (!code) {
    return NextResponse.redirect(`${origin}/login?error=no_code`);
  }

  const supabase = await createServerSupabaseClient();

  const { error } = await supabase.auth.exchangeCodeForSession(code);

  if (error) {
    console.error("Auth callback error:", error.message);
    return NextResponse.redirect(`${origin}/login?error=auth_failed`);
  }

  // Redirect to the page the user originally requested (or home).
  return NextResponse.redirect(`${origin}${next}`);
}
