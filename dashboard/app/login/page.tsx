import { createServerSupabaseClient } from "@/lib/supabase";
import { redirect } from "next/navigation";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { LogIn } from "lucide-react";

export const metadata = {
  title: "Login — NebulosaBot Dashboard",
};

/**
 * Discord OAuth2 login page.
 *
 * Renders a card with a single "Login with Discord" button.
 * The login flow is entirely handled by Supabase Auth:
 *   1. Server Action calls supabase.auth.signInWithOAuth
 *   2. Supabase redirects browser to Discord OAuth2 consent screen
 *   3. Discord redirects back to /api/auth/callback
 *   4. Callback exchanges the code for a Supabase session
 */
export default function LoginPage() {
  async function signInWithDiscord() {
    "use server";

    const supabase = await createServerSupabaseClient();

    const { data, error } = await supabase.auth.signInWithOAuth({
      provider: "discord",
      options: {
        scopes: "identify guilds",
        redirectTo: `${process.env.NEXT_PUBLIC_SITE_URL}/api/auth/callback`,
      },
    });

    if (error) {
      throw new Error(`Discord OAuth2 failed: ${error.message}`);
    }

    if (data.url) {
      redirect(data.url);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <Card className="w-full max-w-sm">
        <CardHeader className="text-center">
          <CardTitle className="text-2xl">NebulosaBot Dashboard</CardTitle>
          <CardDescription>
            Sign in with your Discord account to manage your guilds
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form action={signInWithDiscord}>
            <Button type="submit" className="w-full gap-2">
              <LogIn className="h-4 w-4" />
              Login with Discord
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
