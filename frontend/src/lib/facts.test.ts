import { describe, expect, it } from "vitest";

import { factsFromJson } from "./facts";

describe("factsFromJson", () => {
  const fact = { id: "jt-index", text: "Cut a query from 10.8 ms to 0.35 ms." };

  it("accepts a bare list or a {facts} object", () => {
    expect(factsFromJson(JSON.stringify([fact]))).toEqual([fact]);
    expect(factsFromJson(JSON.stringify({ facts: [fact] }))).toEqual([fact]);
  });

  it("rejects anything else with a readable message", () => {
    expect(() => factsFromJson('{"id": "x"}')).toThrow(/JSON list of facts/);
    expect(() => factsFromJson("not json")).toThrow();
  });
});
