// Typed API client. Calls are made to the app's own /api routes, which are
// proxied server-side to the FastAPI backend (see src/app/api/[...path]).
// The browser therefore never talks to the backend directly and never sees
// the backend API key.
import type {
  ApplicationCreate,
  ApplicationOut,
  ApplicationStatus,
  ApplicationUpdate,
  PipelineStats,
  ResumeCreate,
  ResumeOut,
  TailoredResumeOut,
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
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });

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

export const api = {
  // Applications
  listApplications: (status?: ApplicationStatus) =>
    http<ApplicationOut[]>(
      `/applications${status ? `?status=${status}` : ""}`,
    ),
  getApplication: (id: number) => http<ApplicationOut>(`/applications/${id}`),
  createApplication: (body: ApplicationCreate) =>
    http<ApplicationOut>(`/applications`, {
      method: "POST",
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
  listResumes: () => http<ResumeOut[]>(`/resumes`),
  createResume: (body: ResumeCreate) =>
    http<ResumeOut>(`/resumes`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  // Tailoring
  tailor: (applicationId: number, resumeId?: number) =>
    http<TailoredResumeOut>(`/applications/${applicationId}/tailor`, {
      method: "POST",
      body: JSON.stringify({ resume_id: resumeId ?? null }),
    }),
  listTailored: (applicationId: number) =>
    http<TailoredResumeOut[]>(`/applications/${applicationId}/tailored`),
};
