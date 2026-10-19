// Typed API client. Calls are made to the app's own /api routes, which are
// proxied server-side to the FastAPI backend (see src/app/api/[...path]).
// The browser therefore never talks to the backend directly and never sees
// the backend API key.
import { listPath } from "./pages";
import type {
  ApplicationCreate,
  ResumeContent,
  ApplicationOut,
  ApplicationPage,
  ApplicationStatus,
  ApplicationUpdate,
  AtsReport,
  PipelineStats,
  ResumeCreate,
  ResumeOut,
  ResumePage,
  TailoredResumeOut,
  TailoredResumePage,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  // A file upload (FormData) needs the browser to set its own multipart
  // Content-Type, boundary included; everything else is JSON.
  const json = !(init?.body instanceof FormData);
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: {
      ...(json ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  // Session expired or signed out in another tab: back to the sign-in page.
  if (res.status === 401 && typeof window !== "undefined") {
    // A full reload on purpose: this helper runs outside React, and the reload
    // drops every cached query from the old session.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign("/login");
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body; keep the status text.
    }
    throw new ApiError(detail, res.status);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// A create sent with the same key twice is only performed once by the backend.
// Callers keep one key per user action and reuse it if they retry.
function idempotencyHeader(key?: string): Record<string, string> {
  return key ? { "Idempotency-Key": key } : {};
}

export const api = {
  // Applications
  // Lists are cursor-paginated: pass the previous page's next_cursor.
  listApplications: (status?: ApplicationStatus, cursor?: string) =>
    http<ApplicationPage>(listPath("/applications", { status, cursor })),
  getApplication: (id: number) => http<ApplicationOut>(`/applications/${id}`),
  createApplication: (body: ApplicationCreate, idempotencyKey?: string) =>
    http<ApplicationOut>(`/applications`, {
      method: "POST",
      headers: idempotencyHeader(idempotencyKey),
      body: JSON.stringify(body),
    }),
  updateApplication: (id: number, body: ApplicationUpdate) =>
    http<ApplicationOut>(`/applications/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deleteApplication: (id: number) =>
    http<void>(`/applications/${id}`, { method: "DELETE" }),
  stats: () => http<PipelineStats>(`/applications/stats`),

  // Resumes
  listResumes: (cursor?: string) =>
    http<ResumePage>(listPath("/resumes", { cursor })),
  // Reads a PDF or image into resume content. Saves nothing: the user reviews
  // the result first.
  parseResume: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return http<ResumeContent>(`/resumes/parse`, { method: "POST", body });
  },
  createResume: (body: ResumeCreate, idempotencyKey?: string) =>
    http<ResumeOut>(`/resumes`, {
      method: "POST",
      headers: idempotencyHeader(idempotencyKey),
      body: JSON.stringify(body),
    }),

  // Tailoring
  tailor: (applicationId: number, resumeId?: number, idempotencyKey?: string) =>
    http<TailoredResumeOut>(`/applications/${applicationId}/tailor`, {
      method: "POST",
      headers: idempotencyHeader(idempotencyKey),
      body: JSON.stringify({ resume_id: resumeId ?? null }),
    }),
  // Rule-based ATS readiness of a tailored resume (no LLM call).
  atsCheck: (tailoredId: number) => http<AtsReport>(`/tailored/${tailoredId}/ats`),
  listTailored: (applicationId: number, cursor?: string) =>
    http<TailoredResumePage>(
      listPath(`/applications/${applicationId}/tailored`, { cursor }),
    ),
};
