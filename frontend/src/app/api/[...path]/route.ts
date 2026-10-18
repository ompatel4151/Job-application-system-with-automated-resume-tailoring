// Server-side proxy to the FastAPI backend. The browser calls /api/*; this
// forwards to ${BACKEND_URL}/api/* and attaches the backend API key, which
// stays on the server and is never exposed to the client.
import { NextRequest } from "next/server";

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

  const headers = new Headers();
  const contentType = req.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  // Lets the backend recognize a retried create (see backend/app/idempotency.py).
  const idempotencyKey = req.headers.get("idempotency-key");
  if (idempotencyKey) headers.set("idempotency-key", idempotencyKey);
  // Pass the visitor's IP on, so the backend can rate-limit each visitor
  // separately instead of treating all traffic as coming from this server.
  // The backend only trusts it when TRUST_FORWARDED_FOR is on and the key matches.
  const forwardedFor = req.headers.get("x-forwarded-for");
  if (forwardedFor) headers.set("x-forwarded-for", forwardedFor);
  if (API_KEY) headers.set("x-api-key", API_KEY);

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
    return Response.json(
      { detail: "The backend is unreachable." },
      { status: 502 },
    );
  }

  // Pass through only the headers a client needs.
  const out = new Headers();
  for (const h of ["content-type", "content-disposition"]) {
    const v = res.headers.get(h);
    if (v) out.set(h, v);
  }
  return new Response(res.body, { status: res.status, headers: out });
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
