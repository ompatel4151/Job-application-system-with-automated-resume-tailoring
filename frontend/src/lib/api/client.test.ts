import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api } from "./client";

function mockFetch(status: number, body: unknown) {
  const res = new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(res);
}

afterEach(() => vi.restoreAllMocks());

describe("api client", () => {
  it("calls the app's own /api path and returns parsed JSON", async () => {
    const spy = mockFetch(200, [{ id: 1 }]);
    const result = await api.listApplications();
    expect(result).toEqual([{ id: 1 }]);
    expect(spy).toHaveBeenCalledWith("/api/applications", expect.any(Object));
  });

  it("passes a status filter as a query param", async () => {
    const spy = mockFetch(200, []);
    await api.listApplications("interview");
    expect(spy).toHaveBeenCalledWith(
      "/api/applications?status=interview",
      expect.any(Object),
    );
  });

  it("throws ApiError carrying the backend detail message", async () => {
    mockFetch(502, { detail: "Groq rate limit reached." });
    await expect(api.stats()).rejects.toMatchObject({
      name: "ApiError",
      status: 502,
      message: "Groq rate limit reached.",
    });
  });

  it("returns undefined for 204 responses", async () => {
    mockFetch(204, null);
    await expect(api.deleteApplication(1)).resolves.toBeUndefined();
  });

  it("sends an Idempotency-Key header only when given one", async () => {
    // A fresh Response per call: a response body can only be read once.
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async () => Response.json({ id: 1 }, { status: 201 }));
    const body = { company: "Acme", role: "SWE", status: "saved" as const };

    await api.createApplication(body, "key-123");
    await api.createApplication(body);

    const headersOf = (call: number) =>
      (spy.mock.calls[call][1] as RequestInit).headers as Record<string, string>;
    expect(headersOf(0)["Idempotency-Key"]).toBe("key-123");
    expect(headersOf(1)["Idempotency-Key"]).toBeUndefined();
  });

  it("exposes ApiError as an Error subclass", () => {
    expect(new ApiError("x", 400)).toBeInstanceOf(Error);
  });
});
