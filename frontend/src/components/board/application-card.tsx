"use client";

import Link from "next/link";
import type { ApplicationOut } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export function ApplicationCard({
  application,
  onDragStart,
  dragging,
}: {
  application: ApplicationOut;
  onDragStart: (id: number) => void;
  dragging: boolean;
}) {
  return (
    <Link
      href={`/applications/${application.id}`}
      draggable
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", String(application.id));
        onDragStart(application.id);
      }}
      className={cn(
        "block rounded-lg border bg-card p-3 shadow-sm transition",
        "hover:border-foreground/20 hover:shadow-md cursor-grab active:cursor-grabbing",
        dragging && "opacity-40",
      )}
    >
      <div className="font-medium leading-snug">{application.company}</div>
      <div className="text-sm text-muted-foreground">{application.role}</div>
      <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
        {application.tailored_count > 0 ? (
          <span className="rounded bg-secondary px-1.5 py-0.5 text-secondary-foreground">
            {application.tailored_count} tailored
          </span>
        ) : null}
        {application.job_description ? null : (
          <span className="text-amber-600 dark:text-amber-400">no JD</span>
        )}
      </div>
    </Link>
  );
}
