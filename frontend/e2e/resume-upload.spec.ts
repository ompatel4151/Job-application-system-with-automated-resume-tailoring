import { expect, test } from "@playwright/test";

const parsed = {
  full_name: "Om Patel",
  contact: "om@example.com",
  summary: "Backend engineer.",
  skills: ["Python", "FastAPI"],
  experience: [{ company: "Acme", title: "Intern", dates: "2025", bullets: ["Built tooling."] }],
  projects: [],
  education: [{ school: "Penn State", degree: "BS Computer Science", dates: "2027", details: [] }],
};

test("an uploaded resume fills the form, shows a readable review, and saves it all", async ({ page }) => {
  let saved: Record<string, unknown> | null = null;
  await page.route("**/api/resumes/parse", (route) => route.fulfill({ json: parsed }));
  await page.route("**/api/resumes", (route) => {
    if (route.request().method() === "POST") {
      saved = route.request().postDataJSON();
      return route.fulfill({
        status: 201,
        json: { id: 1, name: "Base resume", is_default: true, content: parsed,
                created_at: "2026-10-19T00:00:00Z", updated_at: "2026-10-19T00:00:00Z" },
      });
    }
    // The list includes the resume once it has been saved, like the backend.
    const items = saved
      ? [{ id: 1, name: "Base resume", is_default: true, content: parsed,
           created_at: "2026-10-19T00:00:00Z", updated_at: "2026-10-19T00:00:00Z" }]
      : [];
    return route.fulfill({ json: { items, next_cursor: null } });
  });
  await page.route("**/api/applications/stats", (route) =>
    route.fulfill({ json: { total: 0, by_status: {} } }),
  );

  await page.goto("/resumes");
  await page.getByLabel("Upload your resume").setInputFiles({
    name: "resume.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4 test"),
  });

  await expect(page.getByLabel("Full name")).toHaveValue("Om Patel");
  await expect(page.getByLabel("Skills (comma-separated)")).toHaveValue("Python, FastAPI");
  await expect(page.getByText("Built tooling.")).toBeVisible();
  await expect(page.getByText("Penn State")).toBeVisible();
  // No JSON on screen unless asked for.
  await expect(page.getByLabel(/Full content JSON/)).toHaveCount(0);

  await page.getByRole("button", { name: "Save as default" }).click();

  await expect.poll(() => saved).not.toBeNull();
  const content = (saved as unknown as { content: typeof parsed }).content;
  expect(content.full_name).toBe("Om Patel");
  expect(content.experience[0].company).toBe("Acme");
  expect(content.education[0].school).toBe("Penn State");

  // And it shows up in the saved list without a reload.
  await expect(page.getByRole("listitem").filter({ hasText: "default" })).toBeVisible();
  await expect(page.getByText("No resumes yet")).toHaveCount(0);
});

test("a failed list load says so instead of showing an empty list", async ({ page }) => {
  await page.route("**/api/resumes", (route) =>
    route.fulfill({ status: 500, json: { detail: "Internal server error", code: "internal_error" } }),
  );
  await page.route("**/api/applications/stats", (route) =>
    route.fulfill({ json: { total: 0, by_status: {} } }),
  );

  await page.goto("/resumes");

  await expect(
    page.getByRole("alert").filter({ hasText: "Could not load your resumes" }),
  ).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("No resumes yet")).toHaveCount(0);
});
