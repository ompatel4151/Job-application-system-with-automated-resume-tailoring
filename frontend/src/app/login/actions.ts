"use server";

import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";

function credentials(form: FormData) {
  return {
    email: String(form.get("email") ?? "").trim(),
    password: String(form.get("password") ?? ""),
  };
}

// Messages go in the URL so the page can show them; never the email address.
function back(kind: "error" | "message", text: string): never {
  redirect(`/login?${kind}=${encodeURIComponent(text)}`);
}

export async function signIn(form: FormData) {
  const supabase = await createClient();
  const { error } = await supabase.auth.signInWithPassword(credentials(form));
  if (error) back("error", error.message);
  redirect("/");
}

export async function signUp(form: FormData) {
  const supabase = await createClient();
  // Supabase only follows redirect URLs on the project's allow list.
  const origin = (await headers()).get("origin") ?? "";
  const { data, error } = await supabase.auth.signUp({
    ...credentials(form),
    options: { emailRedirectTo: `${origin}/auth/callback` },
  });
  if (error) back("error", error.message);
  // With email confirmation on (the Supabase default) there's no session yet.
  if (!data.session) back("message", "Check your email to confirm your account, then sign in.");
  redirect("/");
}

export async function signOut() {
  const supabase = await createClient();
  await supabase.auth.signOut();
  redirect("/login");
}
