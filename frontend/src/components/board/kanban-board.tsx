"use client";

import { useState } from "react";
import { toast } from "sonner";

import { useApplications, useUpdateApplication } from "@/lib/api/hooks";
import type { ApplicationOut, ApplicationStatus } from "@/lib/api/types";
import { STATUSES, STATUS_LABELS } from "@/lib/api/types";
import { STATUS_STYLES } from "@/lib/status";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { ApplicationCard } from "./application-card";

export function KanbanBoard() {
  const { data, isLoading, isError, error } = useApplications();
  const updateApplication = useUpdateApplication();
  const [draggingId, setDraggingId] = useState<number | null>(null);
  const [overStatus, setOverStatus] = useState<ApplicationStatus | null>(null);

  if (isLoading) return <BoardSkeleton />;

  if (isError) {
    return (
      <p className="rounded-md border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
        Could not load applications: {(error as Error).message}
      </p>
    );
  }

  const apps = data ?? [];
  const byStatus = (status: ApplicationStatus): ApplicationOut[] =>
    apps.filter((a) => a.status === status);

  function moveTo(status: ApplicationStatus) {
    const id = draggingId;
    setDraggingId(null);
    setOverStatus(null);
    if (id == null) return;
    const current = apps.find((a) => a.id === id);
    if (!current || current.status === status) return;

    updateApplication.mutate(
      { id, body: { status } },
      {
        onError: (e) => toast.error((e as Error).message),
        onSuccess: () =>
          toast.success(`Moved to ${STATUS_LABELS[status]}`),
      },
    );
  }

  return (
    <div className="flex gap-3 overflow-x-auto pb-4">
      {STATUSES.map((status) => {
        const items = byStatus(status);
        return (
          <div
            key={status}
            onDragOver={(e) => {
              e.preventDefault();
              setOverStatus(status);
            }}
            onDragLeave={() =>
              setOverStatus((s) => (s === status ? null : s))
            }
            onDrop={(e) => {
              e.preventDefault();
              moveTo(status);
            }}
            className={cn(
              "flex w-72 shrink-0 flex-col rounded-xl border bg-muted/30 transition",
              overStatus === status && "border-foreground/30 bg-muted/60",
            )}
          >
            <div className="flex items-center gap-2 px-3 py-2.5">
              <span
                className={cn("h-2 w-2 rounded-full", STATUS_STYLES[status].dot)}
              />
              <span className="text-sm font-medium">
                {STATUS_LABELS[status]}
              </span>
              <span className="ml-auto text-xs text-muted-foreground tabular-nums">
                {items.length}
              </span>
            </div>
            <div className="flex min-h-24 flex-col gap-2 px-2 pb-3">
              {items.map((a) => (
                <ApplicationCard
                  key={a.id}
                  application={a}
                  dragging={draggingId === a.id}
                  onDragStart={setDraggingId}
                />
              ))}
              {items.length === 0 ? (
                <p className="px-1 py-6 text-center text-xs text-muted-foreground">
                  Nothing here yet
                </p>
              ) : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function BoardSkeleton() {
  return (
    <div className="flex gap-3">
      {STATUSES.map((s) => (
        <div key={s} className="w-72 shrink-0 space-y-2 rounded-xl border p-2">
          <Skeleton className="h-6 w-24" />
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      ))}
    </div>
  );
}
