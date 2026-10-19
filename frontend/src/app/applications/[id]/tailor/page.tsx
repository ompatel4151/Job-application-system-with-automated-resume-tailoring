"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { toast } from "sonner";

import {
  useApplication,
  useAtsCheck,
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
  // ponytail: checks only the first page (50 resumes) for a default; the
  // backend still decides, and says so with a 400 if there isn't one.
  const { items: resumes } = useResumes();
  const update = useUpdateApplication();
  const tailor = useTailor();

  // Derive the field from the loaded application until the user edits it, so
  // no effect is needed to seed it.
  const [draft, setDraft] = useState<string | null>(null);
  const jd = draft ?? app?.job_description ?? "";
  const [result, setResult] = useState<TailoredResumeOut | null>(null);
  // One key per "tailor this job description". If the request times out but
  // the backend finished, a retry replays the saved result instead of paying
  // for a second LLM call. Rotated after success and when the JD is edited,
  // because the JD isn't part of the request body the backend fingerprints.
  const [idempotencyKey, setIdempotencyKey] = useState(() => crypto.randomUUID());

  const hasDefaultResume = resumes.some((r) => r.is_default);
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
      const tailored = await tailor.mutateAsync({ applicationId: id, idempotencyKey });
      setResult(tailored);
      setIdempotencyKey(crypto.randomUUID());
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
          onChange={(e) => {
            setDraft(e.target.value);
            setIdempotencyKey(crypto.randomUUID());
          }}
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
          AI match score: how well your experience fits this job, as judged by
          the model.
        </div>
        <div className="ml-auto flex shrink-0 gap-2">
          <a href={`/api/tailored/${result.id}/pdf`}>
            <Button size="sm">Download PDF</Button>
          </a>
          <a href={`/api/tailored/${result.id}/markdown`}>
            <Button variant="outline" size="sm">
              .md
            </Button>
          </a>
        </div>
      </div>

      <AtsPanel tailoredId={result.id} />

      <div className="grid gap-4 sm:grid-cols-2">
        <KeywordList
          title="AI: matched in meaning"
          words={m.matched_keywords}
          className="text-emerald-700 dark:text-emerald-300"
          empty="No strong matches found."
        />
        <KeywordList
          title="AI: missing in meaning"
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

// The rule-based ATS check, computed by the backend from the PDF it would
// download. Kept visibly separate from the AI match score above.
function AtsPanel({ tailoredId }: { tailoredId: number }) {
  const { data: report, isLoading, isError, error } = useAtsCheck(tailoredId);

  if (isLoading) return <Skeleton className="h-40 w-full" />;
  if (isError || !report) {
    return (
      <p role="alert" className="text-sm text-destructive">
        Could not run the ATS check: {(error as Error)?.message}
      </p>
    );
  }

  return (
    <div className="rounded-xl border p-4">
      <div className="flex items-baseline gap-3">
        <h3 className="font-medium">ATS check</h3>
        <span className={cn("text-2xl font-bold tabular-nums", scoreTone(report.score))}>
          {report.score}
          <span className="text-sm text-muted-foreground">/100</span>
        </span>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        Rule-based checks on the PDF above: the same answer every time. Keywords
        here must appear word for word, the way ATS software searches; the AI
        lists below judge meaning, so their counts can differ.
        Real ATS software doesn&apos;t publish a score, so this checks what
        commonly trips it up rather than predicting a result.
      </p>
      <ul className="mt-3 space-y-2 text-sm">
        {report.checks.map((c) => (
          <li key={c.name} className="flex gap-2">
            <span
              aria-label={c.passed ? "passed" : "needs work"}
              className={c.passed ? "text-emerald-600" : "text-amber-600"}
            >
              {c.passed ? "✓" : "!"}
            </span>
            <span className="flex-1">
              <span className="font-medium">{c.label}</span>{" "}
              <span className="text-muted-foreground">{c.detail}</span>
              {c.found && c.found.length > 0 ? (
                <span className="block text-xs text-muted-foreground">
                  Found: {c.found.join(", ")}
                </span>
              ) : null}
              {!c.passed && c.missing && c.missing.length > 0 ? (
                <span className="block text-xs text-muted-foreground">
                  Missing: {c.missing.join(", ")}
                </span>
              ) : null}
            </span>
            <span className="tabular-nums text-muted-foreground">
              {c.points}/{c.max_points}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
