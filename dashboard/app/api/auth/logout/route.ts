import { createServerSupabaseClient } from "@/lib/supabase";
import { NextResponse } from "next/server";

/**
 * Logout handler.
 *
 * Clears the Supabase session cookie and redirects the browser to /login.
 *
 * POST /api/auth/logout
 */
export async function POST() {
  const supabase = await createServerSupabaseClient();

  await supabase.auth.signOut();

  return NextResponse.redirect(new URL("/login", process.env.NEXT_PUBLIC_SITE_URL));
}
