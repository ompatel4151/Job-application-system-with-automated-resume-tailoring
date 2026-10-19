"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";

import { useCreateResume, useParseResume, useResumes } from "@/lib/api/hooks";
import type { ResumeContent } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { LoadMore } from "@/components/load-more";
import { cn } from "@/lib/utils";

// The backend accepts 10 MB, but Vercel won't pass a request body over about
// 4.5 MB to the proxy, so stop larger files here with a clear message.
const MAX_UPLOAD_BYTES = 4 * 1024 * 1024;

export default function ResumesPage() {
  const {
    items: resumes,
    isLoading,
    isError,
    error,
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
  } = useResumes();
  const create = useCreateResume();
  const parse = useParseResume();
  const [advancedOpen, setAdvancedOpen] = useState(false);
  // What the uploaded file was read as. The form fields start from it, and the
  // sections without a field (experience, projects, education) are saved as is.
  const [parsed, setParsed] = useState<ResumeContent | null>(null);
  // Changing the key remounts the form, so its fields pick up new defaults.
  const [formKey, setFormKey] = useState(0);
  // The list is above the form, out of view when you press Save. After a
  // save, scroll up to it and briefly highlight the new resume.
  const savedListRef = useRef<HTMLElement>(null);
  const [justSavedId, setJustSavedId] = useState<number | null>(null);

  function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // choosing the same file again still triggers this
    if (!file) return;
    if (file.size > MAX_UPLOAD_BYTES) {
      toast.error("That file is over 4 MB. Try a smaller PDF or a compressed photo.");
      return;
    }
    parse.mutate(file, {
      onSuccess: (content) => {
        setParsed(content);
        setFormKey((k) => k + 1);
        toast.success("Resume read. Check the details below, then save.");
      },
      onError: (err) => toast.error((err as Error).message),
    });
  }
  // Reused if the user retries after an error; replaced after success.
  const [idempotencyKey, setIdempotencyKey] = useState(() => crypto.randomUUID());

  function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const name = String(form.get("name") ?? "").trim();
    if (!name) return;

    let content: ResumeContent;
    const advanced = String(form.get("advanced") ?? "").trim();
    if (advanced) {
      try {
        content = JSON.parse(advanced) as ResumeContent;
      } catch {
        toast.error("The advanced JSON is not valid JSON.");
        return;
      }
    } else {
      content = {
        experience: [],
        projects: [],
        education: [],
        ...parsed,
        full_name: String(form.get("full_name") ?? "").trim(),
        contact: String(form.get("contact") ?? "").trim(),
        summary: String(form.get("summary") ?? "").trim(),
        skills: String(form.get("skills") ?? "")
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      };
    }

    create.mutate(
      { body: { name, is_default: true, content }, idempotencyKey },
      {
        onSuccess: (resume) => {
          toast.success("Base resume saved");
          setJustSavedId(resume.id);
          setTimeout(() => setJustSavedId(null), 3000);
          savedListRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
          setParsed(null);
          setFormKey((k) => k + 1);
          setAdvancedOpen(false);
          setIdempotencyKey(crypto.randomUUID());
        },
        onError: (err) => toast.error((err as Error).message),
      },
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-6">
      <Link
        href="/"
        className="text-sm text-muted-foreground hover:text-foreground"
      >
        ← Board
      </Link>
      <h1 className="mt-3 text-2xl font-semibold">Base resume</h1>
      <p className="text-muted-foreground">
        Your default base resume is what tailoring rewrites for each job.
      </p>

      <section ref={savedListRef} className="mt-6 scroll-mt-20">
        <h2 className="mb-2 text-sm font-medium text-muted-foreground">
          Saved resumes
        </h2>
        {isLoading ? (
          <Skeleton className="h-12 w-full" />
        ) : isError ? (
          // Not "No resumes yet": a failed load must not look like an empty list.
          <p
            role="alert"
            className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
          >
            Could not load your resumes: {(error as Error).message}
          </p>
        ) : resumes.length > 0 ? (
          <ul className="space-y-2">
            {resumes.map((r) => (
              <li
                key={r.id}
                data-just-saved={r.id === justSavedId || undefined}
                className={cn(
                  "flex items-center justify-between rounded-lg border p-3 text-sm transition-shadow",
                  r.id === justSavedId && "ring-2 ring-emerald-500",
                )}
              >
                <span>{r.name}</span>
                {r.is_default ? (
                  <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
                    default
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">
            No resumes yet. Add one below.
          </p>
        )}
        <LoadMore
          hasNextPage={hasNextPage}
          isFetchingNextPage={isFetchingNextPage}
          fetchNextPage={fetchNextPage}
        />
      </section>

      <section className="mt-8 rounded-xl border p-4">
        <Label htmlFor="resume-file">Upload your resume</Label>
        <p className="mt-1 text-sm text-muted-foreground">
          A PDF or a photo (JPEG, PNG, WebP), up to 4 MB. It&apos;s read into the
          form below for you to check. Nothing is saved until you press Save.
        </p>
        <Input
          id="resume-file"
          type="file"
          accept=".pdf,.jpg,.jpeg,.png,.webp,application/pdf,image/jpeg,image/png,image/webp"
          onChange={onFile}
          disabled={parse.isPending}
          className="mt-3"
        />
        {parse.isPending ? (
          <p role="status" className="mt-2 text-sm text-muted-foreground">
            Reading your resume… this can take up to a minute.
          </p>
        ) : null}
      </section>

      <form
        key={formKey}
        onSubmit={onSubmit}
        className="mt-4 space-y-4 rounded-xl border p-4"
      >
        <div className="space-y-1.5">
          <Label htmlFor="name">Resume name</Label>
          <Input
            id="name"
            name="name"
            required
            defaultValue={parsed ? "Base resume" : undefined}
            placeholder="e.g. Backend engineer base"
          />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="full_name">Full name</Label>
            <Input id="full_name" name="full_name" defaultValue={parsed?.full_name} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="contact">Contact</Label>
            <Input
              id="contact"
              name="contact"
              defaultValue={parsed?.contact}
              placeholder="email · links"
            />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="summary">Summary</Label>
          <Textarea id="summary" name="summary" rows={3} defaultValue={parsed?.summary} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="skills">Skills (comma-separated)</Label>
          <Input
            id="skills"
            name="skills"
            defaultValue={parsed?.skills?.join(", ")}
            placeholder="Python, FastAPI, SQL"
          />
        </div>

        {parsed ? <ParsedSections content={parsed} /> : null}

        <div>
          <button
            type="button"
            onClick={() => setAdvancedOpen((v) => !v)}
            className="text-sm text-primary underline"
          >
            {advancedOpen ? "Hide" : "Paste full resume as JSON (advanced)"}
          </button>
          {advancedOpen ? (
            <div className="mt-2 space-y-1.5">
              <Label htmlFor="advanced">
                Full content JSON (overrides the fields above)
              </Label>
              <Textarea
                id="advanced"
                name="advanced"
                rows={8}
                placeholder='{"full_name": "...", "skills": [], "experience": []}'
              />
            </div>
          ) : null}
        </div>

        <Button type="submit" disabled={create.isPending}>
          {create.isPending ? "Saving…" : "Save as default"}
        </Button>
      </form>
    </div>
  );
}

// The parts of an uploaded resume that have no form field, shown readably so
// the user can check them before saving.
function ParsedSections({ content }: { content: ResumeContent }) {
  const experience = content.experience ?? [];
  const projects = content.projects ?? [];
  const education = content.education ?? [];
  if (!experience.length && !projects.length && !education.length) return null;

  return (
    <div className="space-y-4 rounded-lg bg-muted/40 p-3 text-sm">
      <p className="text-xs text-muted-foreground">
        From your file and saved as shown. To change these, fix the file and
        upload it again, or use the JSON option below.
      </p>
      {experience.length ? (
        <div>
          <h3 className="font-medium">Experience</h3>
          <ul className="mt-1 space-y-2">
            {experience.map((e, i) => (
              <li key={i}>
                <span className="font-medium">{e.title}</span>, {e.company}
                {e.dates ? <span className="text-muted-foreground"> · {e.dates}</span> : null}
                {e.bullets?.length ? (
                  <ul className="ml-4 list-disc">
                    {e.bullets.map((b, j) => (
                      <li key={j}>{b}</li>
                    ))}
                  </ul>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {projects.length ? (
        <div>
          <h3 className="font-medium">Projects</h3>
          <ul className="mt-1 space-y-2">
            {projects.map((p, i) => (
              <li key={i}>
                <span className="font-medium">{p.name}</span>
                {p.description ? <span> · {p.description}</span> : null}
                {p.bullets?.length ? (
                  <ul className="ml-4 list-disc">
                    {p.bullets.map((b, j) => (
                      <li key={j}>{b}</li>
                    ))}
                  </ul>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {education.length ? (
        <div>
          <h3 className="font-medium">Education</h3>
          <ul className="mt-1 space-y-1">
            {education.map((ed, i) => (
              <li key={i}>
                <span className="font-medium">{ed.school}</span>
                {ed.degree ? <span>, {ed.degree}</span> : null}
                {ed.dates ? <span className="text-muted-foreground"> · {ed.dates}</span> : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
