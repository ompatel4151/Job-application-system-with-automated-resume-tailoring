"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";

import {
  useApplication,
  useDeleteApplication,
  useTailored,
  useUpdateApplication,
} from "@/lib/api/hooks";
import type { ApplicationStatus } from "@/lib/api/types";
import { STATUSES, STATUS_LABELS } from "@/lib/api/types";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

function formatDate(value: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export default function ApplicationDetailPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const router = useRouter();

  const { data: app, isLoading, isError, error } = useApplication(id);
  const { data: tailored } = useTailored(id);
  const update = useUpdateApplication();
  const remove = useDeleteApplication();

  if (isLoading) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="mt-4 h-40 w-full" />
      </div>
    );
  }

  if (isError || !app) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-6">
        <p className="text-sm text-destructive">
          Could not load this application: {(error as Error)?.message}
        </p>
        <Link href="/" className="mt-3 inline-block text-sm underline">
          Back to board
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-6">
      <Link
        href="/"
        className="text-sm text-muted-foreground hover:text-foreground"
      >
        ← Board
      </Link>

      <div className="mt-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold leading-tight">
            {app.company}
          </h1>
          <p className="text-muted-foreground">{app.role}</p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={app.status} />
          <Link href={`/applications/${id}/tailor`}>
            <Button size="sm">Tailor resume</Button>
          </Link>
        </div>
      </div>

      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        <Field label="Status">
          <Select
            value={app.status}
            onValueChange={(v) =>
              update.mutate(
                { id, body: { status: v as ApplicationStatus } },
                { onError: (e) => toast.error((e as Error).message) },
              )
            }
          >
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {STATUSES.map((s) => (
                <SelectItem key={s} value={s}>
                  {STATUS_LABELS[s]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field label="Applied">{formatDate(app.applied_at)}</Field>
        <Field label="Job link">
          {app.job_url ? (
            <a
              href={app.job_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary underline break-all"
            >
              {app.job_url}
            </a>
          ) : (
            "—"
          )}
        </Field>
        <Field label="Added">{formatDate(app.created_at)}</Field>
      </div>

      <section className="mt-6">
        <h2 className="mb-2 text-sm font-medium text-muted-foreground">
          Job description
        </h2>
        {app.job_description ? (
          <p className="whitespace-pre-wrap rounded-lg border bg-muted/30 p-4 text-sm">
            {app.job_description}
          </p>
        ) : (
          <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
            No job description yet. Add one from the Tailor view to enable
            tailoring.
          </p>
        )}
      </section>

      <section className="mt-6">
        <h2 className="mb-2 text-sm font-medium text-muted-foreground">
          Tailored resumes ({tailored?.length ?? 0})
        </h2>
        {tailored && tailored.length > 0 ? (
          <ul className="space-y-2">
            {tailored.map((t) => (
              <li
                key={t.id}
                className="flex items-center justify-between rounded-lg border p-3 text-sm"
              >
                <span>
                  Match score{" "}
                  <span className="font-semibold tabular-nums">
                    {t.match_analysis.match_score}
                  </span>
                  /100 · {formatDate(t.created_at)}
                </span>
                <a
                  href={`/api/tailored/${t.id}/markdown`}
                  className="text-primary underline"
                >
                  Download
                </a>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">None yet.</p>
        )}
      </section>

      <Separator />

      <div className="mt-6">
        <Button
          variant="ghost"
          className="text-destructive hover:text-destructive"
          onClick={() => {
            if (!confirm("Delete this application?")) return;
            remove.mutate(id, {
              onSuccess: () => {
                toast.success("Application deleted");
                router.push("/");
              },
              onError: (e) => toast.error((e as Error).message),
            });
          }}
        >
          Delete application
        </Button>
      </div>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 text-sm">{children}</div>
    </div>
  );
}

function Separator() {
  return <div className="mt-8 border-t" />;
}
