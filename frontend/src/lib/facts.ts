import type { Fact } from "@/lib/api/types";

// A sheet file is a JSON list of facts, or {"facts": [...]}. The backend
// validates every field; this only finds the list.
export function factsFromJson(text: string): Fact[] {
  const parsed = JSON.parse(text);
  const facts = Array.isArray(parsed) ? parsed : parsed?.facts;
  if (!Array.isArray(facts)) throw new Error('Expected a JSON list of facts, or {"facts": [...]}.');
  return facts as Fact[];
}
