"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { signOut } from "@/app/login/actions";
import { useStats } from "@/lib/api/hooks";

export function AppHeader() {
  const onLogin = usePathname().startsWith("/login");
  const { data: stats } = useStats(!onLogin);

  return (
    <header className="border-b bg-background/80 backdrop-blur sticky top-0 z-20">
      <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3">
        <Link href="/" className="font-semibold tracking-tight">
          Job Application Tracker
        </Link>
        {onLogin ? null : (
          <nav className="text-sm text-muted-foreground">
            <Link href="/resumes" className="hover:text-foreground">
              Base resume
            </Link>
          </nav>
        )}
        {stats ? (
          <span className="ml-auto text-sm text-muted-foreground tabular-nums">
            {stats.total} total · {stats.by_status.applied} applied ·{" "}
            {stats.by_status.interview} interviewing · {stats.by_status.offer}{" "}
            {stats.by_status.offer === 1 ? "offer" : "offers"}
          </span>
        ) : null}
        {onLogin ? null : (
          <form action={signOut} className={stats ? "" : "ml-auto"}>
            <button
              type="submit"
              className="text-sm text-muted-foreground hover:text-foreground"
            >
              Sign out
            </button>
          </form>
        )}
      </div>
    </header>
  );
}
