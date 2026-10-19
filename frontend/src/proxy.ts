// Runs before every page and /api request: refreshes the Supabase session
// cookie and sends signed-out visitors to /login. This is a convenience, not
// the security boundary: the backend verifies the token on every API call.
import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

const OPEN_PATHS = ["/login", "/auth/"];

export async function proxy(request: NextRequest) {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_PUBLISHABLE_KEY;
  // Not configured (e.g. the mocked e2e run): no sign-in screen. The backend
  // still refuses every /api call that has no valid token.
  if (!url || !key) return NextResponse.next();

  let response = NextResponse.next({ request });
  const supabase = createServerClient(url, key, {
    cookies: {
      getAll: () => request.cookies.getAll(),
      setAll: (toSet, headers) => {
        // Refreshed tokens go to this request (so /api below sees them) and to
        // the browser.
        toSet.forEach(({ name, value }) => request.cookies.set(name, value));
        response = NextResponse.next({ request });
        toSet.forEach(({ name, value, options }) =>
          response.cookies.set(name, value, options),
        );
        Object.entries(headers).forEach(([k, v]) => response.headers.set(k, v));
      },
    },
  });

  // Verifies the token's signature and refreshes it if it has expired.
  const { data } = await supabase.auth.getClaims();
  const signedIn = Boolean(data?.claims);
  const path = request.nextUrl.pathname;
  const isOpen = OPEN_PATHS.some((p) => path.startsWith(p));

  if (!signedIn && !isOpen && !path.startsWith("/api")) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  if (signedIn && path === "/login") {
    return NextResponse.redirect(new URL("/", request.url));
  }
  return response;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
