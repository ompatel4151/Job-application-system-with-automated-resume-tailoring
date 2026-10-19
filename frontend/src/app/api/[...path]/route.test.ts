// @vitest-environment node
import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

afterEach(() => vi.restoreAllMocks());

const ctx = { params: Promise.resolve({ path: ["applications", "7"] }) };

describe("api proxy", () => {
  it("sends one request id to the backend and returns it to the browser", async () => {
    // Like the backend: echo the request id it was sent.
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(async (_url, init) => {
      const id = (init?.headers as Headers).get("x-request-id") ?? "";
      return Response.json({ id: 7 }, { headers: { "x-request-id": id } });
    });
    vi.spyOn(console, "log").mockImplementation(() => {});

    const res = await GET(new NextRequest("http://app.test/api/applications/7"), ctx as never);

    const sent = (fetchSpy.mock.calls[0][1] as RequestInit).headers as Headers;
    const id = sent.get("x-request-id");
    expect(id).toMatch(/^[0-9a-f-]{36}$/);
    expect(res.headers.get("x-request-id")).toBe(id);
  });

  it("logs a JSON line with no ids from the path and no headers", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response(null, { status: 404 }));
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => {});

    await GET(
      new NextRequest("http://app.test/api/applications/7", { headers: { cookie: "secret" } }),
      ctx as never,
    );

    const line = JSON.parse(logSpy.mock.calls[0][0] as string);
    expect(line).toMatchObject({ method: "GET", route: "/api/applications", status: 404 });
    expect(logSpy.mock.calls[0][0]).not.toContain("secret");
    expect(logSpy.mock.calls[0][0]).not.toContain("/7");
  });

  it("answers 502 with a request id when the backend is down", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("fetch failed"));
    vi.spyOn(console, "log").mockImplementation(() => {});

    const res = await GET(new NextRequest("http://app.test/api/applications/7"), ctx as never);

    expect(res.status).toBe(502);
    expect(res.headers.get("x-request-id")).toMatch(/^[0-9a-f-]{36}$/);
  });
});
