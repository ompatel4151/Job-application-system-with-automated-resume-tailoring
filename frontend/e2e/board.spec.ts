import { expect, test } from "@playwright/test";

const application = {
  id: 1,
  company: "DataFlow",
  role: "Senior Backend Engineer",
  status: "applied",
  job_description: "Python, FastAPI, PostgreSQL",
  job_url: null,
  notes: null,
  applied_at: "2026-09-06T00:00:00Z",
  created_at: "2026-09-06T00:00:00Z",
  updated_at: "2026-09-06T00:00:00Z",
  tailored_count: 0,
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/applications/stats", (route) =>
    route.fulfill({
      json: {
        total: 1,
        by_status: {
          saved: 0,
          applied: 1,
          screening: 0,
          interview: 0,
          offer: 0,
          rejected: 0,
        },
      },
    }),
  );
  await page.route("**/api/applications", (route) =>
    route.fulfill({ json: [application] }),
  );
});

test("board renders the pipeline with an application card", async ({
  page,
}) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Pipeline" })).toBeVisible();

  // The seeded application shows up.
  await expect(page.getByText("DataFlow")).toBeVisible();
  await expect(page.getByText("Senior Backend Engineer")).toBeVisible();

  // All six pipeline stages are present as columns.
  for (const stage of [
    "Saved",
    "Applied",
    "Screening",
    "Interview",
    "Offer",
    "Rejected",
  ]) {
    await expect(page.getByText(stage, { exact: true }).first()).toBeVisible();
  }
});
