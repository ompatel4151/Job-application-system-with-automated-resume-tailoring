import { describe, expect, it } from "vitest";

import { STATUSES, STATUS_LABELS } from "./api/types";
import { STATUS_STYLES } from "./status";

describe("status config", () => {
  it("has the six pipeline stages in order", () => {
    expect(STATUSES).toEqual([
      "saved",
      "applied",
      "screening",
      "interview",
      "offer",
      "rejected",
    ]);
  });

  it("has a label and a style for every stage", () => {
    for (const status of STATUSES) {
      expect(STATUS_LABELS[status]).toBeTruthy();
      expect(STATUS_STYLES[status].dot).toBeTruthy();
      expect(STATUS_STYLES[status].badge).toBeTruthy();
    }
  });
});
