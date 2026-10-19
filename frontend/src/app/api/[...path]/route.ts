// Server-side proxy to the FastAPI backend. The browser calls /api/*; this
// forwards to ${BACKEND_URL}/api/* and attaches the backend API key and the
// user's access token. Neither is ever exposed to client-side code.
import { NextRequest } from "next/server";

import { createClient, supabaseEnv } from "@/lib/supabase/server";

// Render's fromService injects a bare hostname; local dev uses a full URL.
// Normalize to an absolute origin either way.
const RAW_BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";
const BACKEND_URL = /^https?:\/\//.test(RAW_BACKEND)
  ? RAW_BACKEND
  : `https://${RAW_BACKEND}`;
const API_KEY = process.env.BACKEND_API_KEY;

// Never cache proxied API responses.
export const dynamic = "force-dynamic";

async function proxy(req: NextRequest, path: string[]): Promise<Response> {
  const target = `${BACKEND_URL}/api/${path.join("/")}${req.nextUrl.search}`;

  // One ID per request, sent to the backend and logged on both sides, so a
  // request can be followed from the Vercel logs into the backend logs.
  const requestId = crypto.randomUUID();
  const started = Date.now();
  const headers = new Headers({ "x-request-id": requestId });
  const contentType = req.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  // Lets the backend recognize a retried create (see backend/app/idempotency.py).
  const idempotencyKey = req.headers.get("idempotency-key");
  if (idempotencyKey) headers.set("idempotency-key", idempotencyKey);
  if (API_KEY) headers.set("x-api-key", API_KEY);
  // The signed-in user's access token, from the session cookie. The backend
  // verifies its signature, so reading it unverified here is fine.
  if (supabaseEnv()) {
    const { data } = await (await createClient()).auth.getSession();
    if (data.session) headers.set("authorization", `Bearer ${data.session.access_token}`);
  }

  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  const body = hasBody ? await req.arrayBuffer() : undefined;

  let res: Response;
  try {
    res = await fetch(target, {
      method: req.method,
      headers,
      body,
      cache: "no-store",
    });
  } catch {
    log(requestId, req.method, path, 502, started);
    return Response.json(
      { detail: "The backend is unreachable." },
      { status: 502, headers: { "x-request-id": requestId } },
    );
  }
  log(requestId, req.method, path, res.status, started);

  // Pass through only the headers a client needs.
  const out = new Headers();
  // retry-after: how long to wait after a 429 (rate limit).
  // idempotent-replayed: marks a retried create that was answered from storage.
  // x-request-id: quote it when reporting a problem.
  for (const h of [
    "content-type",
    "content-disposition",
    "retry-after",
    "idempotent-replayed",
    "x-request-id",
  ]) {
    const v = res.headers.get(h);
    if (v) out.set(h, v);
  }
  return new Response(res.body, { status: res.status, headers: out });
}

// A JSON line per proxied call. The path's first segment only (no ids), and
// never headers, so no tokens or personal data end up in the logs.
function log(requestId: string, method: string, path: string[], status: number, started: number) {
  console.log(
    JSON.stringify({
      request_id: requestId,
      method,
      route: `/api/${path[0] ?? ""}`,
      status,
      duration_ms: Date.now() - started,
    }),
  );
}

const handler = async (
  req: NextRequest,
  ctx: RouteContext<"/api/[...path]">,
) => {
  const { path } = await ctx.params;
  return proxy(req, path);
};

export {
  handler as GET,
  handler as POST,
  handler as PUT,
  handler as PATCH,
  handler as DELETE,
};
