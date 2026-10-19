import { expect, test } from "@playwright/test";

const now = "2026-10-19T00:00:00Z";
const application = {
  id: 1, company: "Globex", role: "Backend Engineer", status: "saved",
  job_description: "Python, PostgreSQL, Kubernetes", job_url: null, notes: null,
  applied_at: null, created_at: now, updated_at: now, tailored_count: 0,
};
const content = { full_name: "Om Patel", contact: "", summary: "", skills: [], experience: [], projects: [], education: [] };

test("a tailored resume offers a PDF and shows the ATS check apart from the AI score", async ({ page }) => {
  await page.route("**/api/applications/1", (r) => r.fulfill({ json: application }));
  await page.route("**/api/resumes", (r) =>
    r.fulfill({ json: { items: [{ id: 1, name: "Base", is_default: true, content, created_at: now, updated_at: now }], next_cursor: null } }),
  );
  await page.route("**/api/applications/stats", (r) => r.fulfill({ json: { total: 1, by_status: {} } }));
  await page.route("**/api/applications/1/tailor", (r) =>
    r.fulfill({
      status: 201,
      json: {
        id: 42, application_id: 1, resume_id: 1, content, markdown: "# Om Patel\\n", created_at: now,
        match_analysis: { match_score: 76, matched_keywords: ["Python"], missing_keywords: ["Kubernetes"], recommendations: [] },
      },
    }),
  );
  await page.route("**/api/tailored/42/ats", (r) =>
    r.fulfill({
      json: {
        score: 82,
        checks: [
          { name: "parse", label: "Text reads back from the PDF", passed: true, points: 25, max_points: 25, detail: "All text reads back from the PDF (5 sections).", missing: [] },
          { name: "keywords", label: "Job keywords (word for word)", passed: false, points: 23, max_points: 35, detail: "2 of 3 terms from the job posting appear word for word.", missing: ["Kubernetes"], found: ["Python", "PostgreSQL"] },
        ],
      },
    }),
  );

  await page.goto("/applications/1/tailor");
  await page.getByRole("button", { name: "Tailor resume" }).click();

  await expect(page.getByRole("link", { name: "Download PDF" })).toHaveAttribute("href", "/api/tailored/42/pdf");
  await expect(page.getByRole("heading", { name: "ATS check" })).toBeVisible();
  await expect(page.getByText("82/100")).toBeVisible();
  await expect(page.getByText("Found: Python, PostgreSQL")).toBeVisible();
  await expect(page.getByText("Missing: Kubernetes")).toBeVisible();
  await expect(page.getByText("AI: matched in meaning (1)")).toBeVisible();
  // The AI score is still there, labelled as a different thing.
  await expect(page.getByText(/AI match score/)).toBeVisible();
});
