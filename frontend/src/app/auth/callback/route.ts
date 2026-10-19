// The link in Supabase's confirmation email lands here with a one-time code,
// which is swapped for a session cookie.
import { NextResponse, type NextRequest } from "next/server";

import { createClient } from "@/lib/supabase/server";

export async function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get("code");
  if (code) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) return NextResponse.redirect(new URL("/", request.url));
  }
  const login = new URL("/login", request.url);
  login.searchParams.set("error", "That link is invalid or has expired. Sign in, or sign up again.");
  return NextResponse.redirect(login);
}
