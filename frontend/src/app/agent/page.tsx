"use client";

import { useState } from "react";
import { toast } from "sonner";

import {
  useCreateMemory,
  useDeleteFact,
  useDeleteMemory,
  useFacts,
  useMemories,
  useReplaceFacts,
} from "@/lib/api/hooks";
import { factsFromJson } from "@/lib/facts";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";

export default function AgentPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-10 px-4 py-6">
      <FactSheet />
      <Memories />
    </div>
  );
}

function FactSheet() {
  const { data: facts, isLoading } = useFacts();
  const replace = useReplaceFacts();
  const remove = useDeleteFact();

  async function upload(file: File) {
    try {
      const saved = await replace.mutateAsync(factsFromJson(await file.text()));
      if (saved.indexed) toast.success(`Saved ${saved.saved} facts`);
      else
        toast.warning(
          `Saved ${saved.saved} facts, but search isn't available, so tailoring uses plain mode for now.`,
        );
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  return (
    <section>
      <h1 className="text-2xl font-semibold">Fact sheet</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Verified facts about your work. In agent mode, every new bullet must cite
        facts from this sheet, and a bullet that uses a number or tool its facts
        don&apos;t contain is rewritten once, then dropped. Uploading replaces the
        whole sheet.
      </p>
      <label className="mt-4 inline-flex">
        <span className="sr-only">Upload fact sheet (JSON)</span>
        <input
          type="file"
          accept="application/json,.json"
          disabled={replace.isPending}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void upload(file);
            e.target.value = "";
          }}
          className="text-sm file:mr-3 file:rounded-md file:border file:bg-background file:px-3 file:py-1.5"
        />
      </label>
      <p className="mt-1 text-xs text-muted-foreground">
        Each fact: {'{"id": "jt-index", "text": "...", "numbers": ["10.8 ms"], "tools": ["PostgreSQL"], "context": "..."}'}
      </p>

      {isLoading ? (
        <Skeleton className="mt-4 h-24 w-full" />
      ) : facts && facts.length > 0 ? (
        <ul className="mt-4 divide-y rounded-lg border">
          {facts.map((f) => (
            <li key={f.id} className="flex gap-3 p-3 text-sm">
              <div className="flex-1">
                <span className="font-mono text-xs text-muted-foreground">{f.id}</span>
                <p>{f.text}</p>
                {f.tools && f.tools.length > 0 ? (
                  <p className="text-xs text-muted-foreground">Tools: {f.tools.join(", ")}</p>
                ) : null}
              </div>
              <Button
                variant="outline"
                size="sm"
                disabled={remove.isPending}
                onClick={() => remove.mutate(f.id)}
                aria-label={`Delete fact ${f.id}`}
              >
                Delete
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-4 text-sm text-muted-foreground">No facts yet.</p>
      )}
    </section>
  );
}

function Memories() {
  const { data: memories, isLoading } = useMemories();
  const create = useCreateMemory();
  const remove = useDeleteMemory();
  const [text, setText] = useState("");

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    try {
      await create.mutateAsync(text.trim());
      setText("");
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  return (
    <section>
      <h2 className="text-xl font-semibold">Memories</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Preferences the agent follows, like &quot;keep bullets to one line&quot;.
        Only you write these; the agent never adds to them.
      </p>
      <form onSubmit={add} className="mt-3 flex gap-2">
        <Textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={500}
          rows={2}
          placeholder="Add a preference…"
          aria-label="New memory"
        />
        <Button type="submit" disabled={create.isPending || !text.trim()}>
          Add
        </Button>
      </form>
      {isLoading ? (
        <Skeleton className="mt-4 h-16 w-full" />
      ) : memories && memories.length > 0 ? (
        <ul className="mt-4 divide-y rounded-lg border">
          {memories.map((m) => (
            <li key={m.id} className="flex items-center gap-3 p-3 text-sm">
              <span className="flex-1">{m.text}</span>
              <Button
                variant="outline"
                size="sm"
                disabled={remove.isPending}
                onClick={() => remove.mutate(m.id)}
                aria-label={`Delete memory: ${m.text}`}
              >
                Delete
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-4 text-sm text-muted-foreground">No memories yet.</p>
      )}
    </section>
  );
}
