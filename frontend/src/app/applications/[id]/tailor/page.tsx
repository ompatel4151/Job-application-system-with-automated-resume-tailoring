"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { toast } from "sonner";

import {
  useApplication,
  useResumes,
  useTailor,
  useUpdateApplication,
} from "@/lib/api/hooks";
import type { TailoredResumeOut } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

function scoreTone(score: number) {
  if (score >= 75) return "text-emerald-600 dark:text-emerald-400";
  if (score >= 50) return "text-amber-600 dark:text-amber-400";
  return "text-rose-600 dark:text-rose-400";
}

export default function TailorPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);

  const { data: app, isLoading } = useApplication(id);
  const { data: resumes } = useResumes();
  const update = useUpdateApplication();
  const tailor = useTailor();

  // Derive the field from the loaded application until the user edits it, so
  // no effect is needed to seed it.
  const [draft, setDraft] = useState<string | null>(null);
  const jd = draft ?? app?.job_description ?? "";
  const [result, setResult] = useState<TailoredResumeOut | null>(null);

  const hasDefaultResume = (resumes ?? []).some((r) => r.is_default);
  const busy = tailor.isPending || update.isPending;

  async function runTailor() {
    if (!jd.trim()) {
      toast.error("Paste a job description first.");
      return;
    }
    try {
      if (app && jd !== (app.job_description ?? "")) {
        await update.mutateAsync({ id, body: { job_description: jd } });
      }
      const tailored = await tailor.mutateAsync({ applicationId: id });
      setResult(tailored);
      toast.success("Resume tailored");
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  if (isLoading) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="mt-4 h-48 w-full" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-6">
      <Link
        href={`/applications/${id}`}
        className="text-sm text-muted-foreground hover:text-foreground"
      >
        ← {app?.company}
      </Link>
      <h1 className="mt-3 text-2xl font-semibold">Tailor resume</h1>
      <p className="text-muted-foreground">
        {app?.role} at {app?.company}
      </p>

      {!hasDefaultResume ? (
        <p className="mt-4 rounded-lg border border-amber-500/40 bg-amber-500/5 p-3 text-sm">
          You have no default base resume yet.{" "}
          <Link href="/resumes" className="underline">
            Add one
          </Link>{" "}
          so tailoring has something to work from.
        </p>
      ) : null}

      <section className="mt-6">
        <label className="mb-2 block text-sm font-medium text-muted-foreground">
          Job description
        </label>
        <Textarea
          value={jd}
          onChange={(e) => setDraft(e.target.value)}
          rows={8}
          placeholder="Paste the job description here…"
        />
        <div className="mt-3">
          <Button onClick={runTailor} disabled={busy || !hasDefaultResume}>
            {busy ? "Tailoring…" : "Tailor resume"}
          </Button>
        </div>
      </section>

      {result ? <TailorResult result={result} /> : null}
    </div>
  );
}

function TailorResult({ result }: { result: TailoredResumeOut }) {
  const m = result.match_analysis;
  return (
    <section className="mt-8 space-y-6">
      <div className="flex items-center gap-4 rounded-xl border p-4">
        <div className={cn("text-4xl font-bold tabular-nums", scoreTone(m.match_score))}>
          {m.match_score}
          <span className="text-lg text-muted-foreground">/100</span>
        </div>
        <div className="text-sm text-muted-foreground">
          Fit score for this job. Higher means the base resume already lines up
          with what the posting asks for.
        </div>
        <a
          href={`/api/tailored/${result.id}/markdown`}
          className="ml-auto shrink-0"
        >
          <Button variant="outline" size="sm">
            Download .md
          </Button>
        </a>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <KeywordList
          title="Matched"
          words={m.matched_keywords}
          className="text-emerald-700 dark:text-emerald-300"
          empty="No strong matches found."
        />
        <KeywordList
          title="Missing"
          words={m.missing_keywords}
          className="text-rose-700 dark:text-rose-300"
          empty="Nothing important missing."
        />
      </div>

      {m.recommendations.length > 0 ? (
        <div>
          <h3 className="mb-2 text-sm font-medium text-muted-foreground">
            Recommendations
          </h3>
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {m.recommendations.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div>
        <h3 className="mb-2 text-sm font-medium text-muted-foreground">
          Tailored resume
        </h3>
        <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-lg border bg-muted/30 p-4 text-sm">
          {result.markdown}
        </pre>
      </div>
    </section>
  );
}

function KeywordList({
  title,
  words,
  className,
  empty,
}: {
  title: string;
  words: string[];
  className?: string;
  empty: string;
}) {
  return (
    <div>
      <h3 className="mb-2 text-sm font-medium text-muted-foreground">
        {title} ({words.length})
      </h3>
      {words.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {words.map((w) => (
            <span
              key={w}
              className={cn(
                "rounded-full border px-2 py-0.5 text-xs",
                className,
              )}
            >
              {w}
            </span>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">{empty}</p>
      )}
    </div>
  );
}
