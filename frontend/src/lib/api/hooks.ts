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

export function useStats(enabled = true) {
  return useQuery({ queryKey: keys.stats, queryFn: () => api.stats(), enabled });
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
    mutationFn: ({
      body,
      idempotencyKey,
    }: {
      body: ApplicationCreate;
      idempotencyKey?: string;
    }) => api.createApplication(body, idempotencyKey),
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
    mutationFn: ({
      body,
      idempotencyKey,
    }: {
      body: ResumeCreate;
      idempotencyKey?: string;
    }) => api.createResume(body, idempotencyKey),
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
      idempotencyKey,
    }: {
      applicationId: number;
      resumeId?: number;
      idempotencyKey?: string;
    }) => api.tailor(applicationId, resumeId, idempotencyKey),
    onSuccess: (tailored) => {
      invalidate();
      qc.invalidateQueries({ queryKey: keys.tailored(tailored.application_id) });
    },
  });
}
