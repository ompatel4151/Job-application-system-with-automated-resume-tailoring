import { describe, expect, it } from "vitest";

import { flattenPages, listPath, nextPageParam } from "./pages";

const page = (ids: number[], next: string | null) => ({
  items: ids.map((id) => ({ id })),
  next_cursor: next,
});

describe("cursor pages", () => {
  it("asks for the next page until the cursor runs out", () => {
    expect(nextPageParam(page([1], "abc"))).toBe("abc");
    expect(nextPageParam(page([1], null))).toBeUndefined();
  });

  it("flattens pages in order and drops a row seen twice", () => {
    const data = { pages: [page([5, 4], "c1"), page([4, 3], null)], pageParams: [] };
    expect(flattenPages(data).map((r) => r.id)).toEqual([5, 4, 3]);
    expect(flattenPages(undefined)).toEqual([]);
  });

  it("builds query strings without empty params", () => {
    expect(listPath("/applications", { status: undefined, cursor: undefined })).toBe("/applications");
    expect(listPath("/applications", { status: "offer", cursor: "c" })).toBe(
      "/applications?status=offer&cursor=c",
    );
  });
});
