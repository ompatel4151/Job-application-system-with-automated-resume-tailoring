import { expect, test } from "@playwright/test";

test("sign-in page offers sign in and account creation", async ({ page }) => {
  await page.goto("/login");

  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await expect(page.getByLabel("Email")).toBeVisible();
  await expect(page.getByLabel("Password")).toBeVisible();
  await expect(page.getByRole("button", { name: "Create account" })).toBeVisible();
  // No pipeline stats or nav while signed out.
  await expect(page.getByRole("link", { name: "Base resume" })).toHaveCount(0);
});

test("errors from a failed sign-in are shown", async ({ page }) => {
  await page.goto("/login?error=Invalid%20login%20credentials");

  await expect(page.getByRole("alert")).toHaveText("Invalid login credentials");
});
