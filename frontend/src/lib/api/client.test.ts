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
  it("calls the app's own /api path and returns the parsed page", async () => {
    const page = { items: [{ id: 1 }], next_cursor: "c1" };
    const spy = mockFetch(200, page);
    const result = await api.listApplications();
    expect(result).toEqual(page);
    expect(spy).toHaveBeenCalledWith("/api/applications", expect.any(Object));
  });

  it("passes the status filter and cursor as query params", async () => {
    const spy = mockFetch(200, { items: [], next_cursor: null });
    await api.listApplications("interview", "c1");
    expect(spy).toHaveBeenCalledWith(
      "/api/applications?status=interview&cursor=c1",
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

  it("uploads a resume file as multipart, not JSON", async () => {
    const spy = mockFetch(200, { full_name: "Om" });
    const file = new File(["%PDF-1.4"], "resume.pdf", { type: "application/pdf" });

    await expect(api.parseResume(file)).resolves.toEqual({ full_name: "Om" });

    const init = spy.mock.calls[0][1] as RequestInit;
    expect(spy.mock.calls[0][0]).toBe("/api/resumes/parse");
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get("file")).toBe(file);
    // The browser must set multipart/form-data with its boundary itself.
    expect((init.headers as Record<string, string>)["Content-Type"]).toBeUndefined();
  });

  it("asks the backend for a tailored resume's ATS check", async () => {
    const spy = mockFetch(200, { score: 80, checks: [] });

    await expect(api.atsCheck(7)).resolves.toEqual({ score: 80, checks: [] });
    expect(spy).toHaveBeenCalledWith("/api/tailored/7/ats", expect.any(Object));
  });
});
