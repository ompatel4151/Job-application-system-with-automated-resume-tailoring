// Helpers for the backend's cursor-paginated list endpoints.
import type { InfiniteData } from "@tanstack/react-query";

export type Page<T> = { items: T[]; next_cursor: string | null };

// ponytail: Vercel and Render deploy separately, so for a few minutes this
// frontend may talk to a backend that still returns a plain array. Remove
// once both sides run the paginated API.
export function toPage<T>(body: Page<T> | T[]): Page<T> {
  return Array.isArray(body) ? { items: body, next_cursor: null } : body;
}

// The cursor for the next page, or undefined to tell TanStack Query to stop.
export function nextPageParam<T>(last: Page<T>): string | undefined {
  return last.next_cursor ?? undefined;
}

// All loaded pages as one list. A row whose sort key changed while paging
// (e.g. a card moved, which bumps updated_at) can arrive twice; keep the first.
export function flattenPages<T extends { id: number }>(
  data: InfiniteData<Page<T>> | undefined,
): T[] {
  const seen = new Set<number>();
  const out: T[] = [];
  for (const page of data?.pages ?? []) {
    for (const item of page.items) {
      if (!seen.has(item.id)) {
        seen.add(item.id);
        out.push(item);
      }
    }
  }
  return out;
}

export function listPath(base: string, params: Record<string, string | undefined>) {
  const query = new URLSearchParams(
    Object.entries(params).filter((e): e is [string, string] => Boolean(e[1])),
  ).toString();
  return query ? `${base}?${query}` : base;
}
