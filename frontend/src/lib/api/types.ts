// Convenience aliases over the generated OpenAPI schema, so the rest of the
// app imports readable names that still track the backend contract.
import type { components } from "./schema";

export type ApplicationStatus = components["schemas"]["ApplicationStatus"];
export type ApplicationOut = components["schemas"]["ApplicationOut"];
export type ApplicationCreate = components["schemas"]["ApplicationCreate"];
export type ApplicationUpdate = components["schemas"]["ApplicationUpdate"];

export type ResumeOut = components["schemas"]["ResumeOut"];
export type ResumeCreate = components["schemas"]["ResumeCreate"];
export type ResumeContent = components["schemas"]["ResumeContent"];

export type TailoredResumeOut = components["schemas"]["TailoredResumeOut"];
export type MatchAnalysis = components["schemas"]["MatchAnalysis"];
export type PipelineStats = components["schemas"]["PipelineStats"];

// The six pipeline stages, in board order.
export const STATUSES: ApplicationStatus[] = [
  "saved",
  "applied",
  "screening",
  "interview",
  "offer",
  "rejected",
];

export const STATUS_LABELS: Record<ApplicationStatus, string> = {
  saved: "Saved",
  applied: "Applied",
  screening: "Screening",
  interview: "Interview",
  offer: "Offer",
  rejected: "Rejected",
};
