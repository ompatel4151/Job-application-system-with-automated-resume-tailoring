"use client";

// TanStack Query hooks over the typed client. Query keys and the invalidation
// they trigger live here so the screens stay declarative.
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { api } from "./client";
import { flattenPages, nextPageParam } from "./pages";
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

// List hooks load pages on demand; `items` is every loaded page as one list.
export function useApplications() {
  const query = useInfiniteQuery({
    queryKey: keys.applications,
    queryFn: ({ pageParam }) => api.listApplications(undefined, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: nextPageParam,
  });
  return { ...query, items: flattenPages(query.data) };
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
  const query = useInfiniteQuery({
    queryKey: keys.resumes,
    queryFn: ({ pageParam }) => api.listResumes(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: nextPageParam,
  });
  return { ...query, items: flattenPages(query.data) };
}

export function useTailored(applicationId: number) {
  const query = useInfiniteQuery({
    queryKey: keys.tailored(applicationId),
    queryFn: ({ pageParam }) => api.listTailored(applicationId, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: nextPageParam,
  });
  return { ...query, items: flattenPages(query.data) };
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

export function useParseResume() {
  return useMutation({ mutationFn: (file: File) => api.parseResume(file) });
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
