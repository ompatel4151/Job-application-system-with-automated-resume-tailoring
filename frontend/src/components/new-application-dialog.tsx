"use client";

import { useState } from "react";
import { toast } from "sonner";

import { useCreateApplication } from "@/lib/api/hooks";
import type { ApplicationStatus } from "@/lib/api/types";
import { STATUSES, STATUS_LABELS } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export function NewApplicationDialog() {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<ApplicationStatus>("saved");
  const create = useCreateApplication();

  function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const company = String(form.get("company") ?? "").trim();
    const role = String(form.get("role") ?? "").trim();
    if (!company || !role) return;

    create.mutate(
      {
        company,
        role,
        status,
        job_url: String(form.get("job_url") ?? "").trim() || null,
        job_description:
          String(form.get("job_description") ?? "").trim() || null,
      },
      {
        onSuccess: () => {
          toast.success("Application added");
          setOpen(false);
          setStatus("saved");
        },
        onError: (err) => toast.error((err as Error).message),
      },
    );
  }

  return (
    <>
      <Button onClick={() => setOpen(true)}>Add application</Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>New application</DialogTitle>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="company">Company</Label>
              <Input id="company" name="company" required autoFocus />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="role">Role</Label>
              <Input id="role" name="role" required />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Status</Label>
              <Select
                value={status}
                onValueChange={(v) => setStatus(v as ApplicationStatus)}
              >
                <SelectTrigger>
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
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="job_url">Job URL</Label>
              <Input id="job_url" name="job_url" placeholder="https://…" />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="job_description">
              Job description{" "}
              <span className="text-muted-foreground">(used for tailoring)</span>
            </Label>
            <Textarea id="job_description" name="job_description" rows={5} />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? "Adding…" : "Add application"}
            </Button>
          </DialogFooter>
        </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
