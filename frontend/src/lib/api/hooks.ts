"use client";

// TanStack Query hooks over the typed client. Query keys and the invalidation
// they trigger live here so the screens stay declarative.
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { api } from "./client";
import type {
  ApplicationCreate,
  ApplicationStatus,
  ApplicationUpdate,
  ResumeCreate,
} from "./types";

export const keys = {
  applications: ["applications"] as const,
  application: (id: number) => ["application", id] as const,
  stats: ["stats"] as const,
  resumes: ["resumes"] as const,
  tailored: (id: number) => ["tailored", id] as const,
};

export function useApplications() {
  return useQuery({
    queryKey: keys.applications,
    queryFn: () => api.listApplications(),
  });
}

export function useApplication(id: number) {
  return useQuery({
    queryKey: keys.application(id),
    queryFn: () => api.getApplication(id),
  });
}

export function useStats() {
  return useQuery({ queryKey: keys.stats, queryFn: () => api.stats() });
}

export function useResumes() {
  return useQuery({ queryKey: keys.resumes, queryFn: () => api.listResumes() });
}

export function useTailored(applicationId: number) {
  return useQuery({
    queryKey: keys.tailored(applicationId),
    queryFn: () => api.listTailored(applicationId),
  });
}

// A shared invalidation for anything that changes an application.
function useInvalidateApplications() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: keys.applications });
    qc.invalidateQueries({ queryKey: keys.stats });
  };
}

export function useCreateApplication() {
  const invalidate = useInvalidateApplications();
  return useMutation({
    mutationFn: (body: ApplicationCreate) => api.createApplication(body),
    onSuccess: invalidate,
  });
}

export function useUpdateApplication() {
  const qc = useQueryClient();
  const invalidate = useInvalidateApplications();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: ApplicationUpdate }) =>
      api.updateApplication(id, body),
    onSuccess: (updated) => {
      invalidate();
      qc.invalidateQueries({ queryKey: keys.application(updated.id) });
    },
  });
}

export function useDeleteApplication() {
  const invalidate = useInvalidateApplications();
  return useMutation({
    mutationFn: (id: number) => api.deleteApplication(id),
    onSuccess: invalidate,
  });
}

export function useCreateResume() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ResumeCreate) => api.createResume(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.resumes }),
  });
}

export function useTailor() {
  const qc = useQueryClient();
  const invalidate = useInvalidateApplications();
  return useMutation({
    mutationFn: ({
      applicationId,
      resumeId,
    }: {
      applicationId: number;
      resumeId?: number;
      // status is only used by callers to know which status the app moved to
      status?: ApplicationStatus;
    }) => api.tailor(applicationId, resumeId),
    onSuccess: (tailored) => {
      invalidate();
      qc.invalidateQueries({ queryKey: keys.tailored(tailored.application_id) });
    },
  });
}
