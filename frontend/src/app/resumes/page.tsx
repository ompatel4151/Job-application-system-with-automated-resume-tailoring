"use client";

import { useState } from "react";
import Link from "next/link";
import { toast } from "sonner";

import { useCreateResume, useResumes } from "@/lib/api/hooks";
import type { ResumeContent } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";

export default function ResumesPage() {
  const { data: resumes, isLoading } = useResumes();
  const create = useCreateResume();
  const [advancedOpen, setAdvancedOpen] = useState(false);

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
        full_name: String(form.get("full_name") ?? "").trim(),
        contact: String(form.get("contact") ?? "").trim(),
        summary: String(form.get("summary") ?? "").trim(),
        skills: String(form.get("skills") ?? "")
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        experience: [],
        projects: [],
        education: [],
      };
    }

    create.mutate(
      { name, is_default: true, content },
      {
        onSuccess: () => {
          toast.success("Base resume saved");
          (e.target as HTMLFormElement).reset();
          setAdvancedOpen(false);
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

      <section className="mt-6">
        <h2 className="mb-2 text-sm font-medium text-muted-foreground">
          Saved resumes
        </h2>
        {isLoading ? (
          <Skeleton className="h-12 w-full" />
        ) : resumes && resumes.length > 0 ? (
          <ul className="space-y-2">
            {resumes.map((r) => (
              <li
                key={r.id}
                className="flex items-center justify-between rounded-lg border p-3 text-sm"
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
      </section>

      <form
        onSubmit={onSubmit}
        className="mt-8 space-y-4 rounded-xl border p-4"
      >
        <div className="space-y-1.5">
          <Label htmlFor="name">Resume name</Label>
          <Input
            id="name"
            name="name"
            required
            placeholder="e.g. Backend engineer base"
          />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="full_name">Full name</Label>
            <Input id="full_name" name="full_name" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="contact">Contact</Label>
            <Input id="contact" name="contact" placeholder="email · links" />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="summary">Summary</Label>
          <Textarea id="summary" name="summary" rows={3} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="skills">Skills (comma-separated)</Label>
          <Input id="skills" name="skills" placeholder="Python, FastAPI, SQL" />
        </div>

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
