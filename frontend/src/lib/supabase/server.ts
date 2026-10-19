// Supabase Auth, server side only. Sign-in runs in server actions and the
// session lives in cookies, so the browser never loads Supabase code and the
// two settings below are read at runtime (no rebuild to change them).
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

export function supabaseEnv() {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_PUBLISHABLE_KEY;
  return url && key ? { url, key } : null;
}

export async function createClient() {
  const env = supabaseEnv();
  if (!env) throw new Error("SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY must be set.");
  const cookieStore = await cookies();
  return createServerClient(env.url, env.key, {
    cookies: {
      getAll: () => cookieStore.getAll(),
      setAll: (toSet) => {
        try {
          toSet.forEach(({ name, value, options }) =>
            cookieStore.set(name, value, options),
          );
        } catch {
          // Read-only during a Server Component render; the proxy refreshes
          // the cookies on the next request instead.
        }
      },
    },
  });
}
