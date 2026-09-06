import type { ApplicationStatus } from "./api/types";

// Per-stage accent classes, tuned to read in light and dark. `dot` colors the
// column header marker; `badge` styles the status pill.
export const STATUS_STYLES: Record<
  ApplicationStatus,
  { dot: string; badge: string }
> = {
  saved: {
    dot: "bg-slate-400",
    badge:
      "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  },
  applied: {
    dot: "bg-blue-500",
    badge: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  },
  screening: {
    dot: "bg-violet-500",
    badge:
      "bg-violet-100 text-violet-700 dark:bg-violet-950 dark:text-violet-300",
  },
  interview: {
    dot: "bg-amber-500",
    badge: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  },
  offer: {
    dot: "bg-emerald-500",
    badge:
      "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  },
  rejected: {
    dot: "bg-rose-500",
    badge: "bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300",
  },
};
