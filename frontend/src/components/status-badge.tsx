import { cn } from "@/lib/utils";
import type { ApplicationStatus } from "@/lib/api/types";
import { STATUS_LABELS } from "@/lib/api/types";
import { STATUS_STYLES } from "@/lib/status";

export function StatusBadge({
  status,
  className,
}: {
  status: ApplicationStatus;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        STATUS_STYLES[status].badge,
        className,
      )}
    >
      {STATUS_LABELS[status]}
    </span>
  );
}
