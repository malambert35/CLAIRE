import { expect, test } from "@playwright/test";

test("sign in, family navigation, localization, theme and revocation", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(page).toHaveTitle("CLAIRE — Family archive");
  await page.getByLabel("Email", { exact: true }).fill("alice@example.test");
  await page
    .getByLabel("Password", { exact: true })
    .fill("synthetic-browser-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "A place for your family stories" }),
  ).toBeVisible();
  await page.screenshot({ path: "../../data/desktop.png", fullPage: true });
  await page
    .getByRole("button", { name: "Family Members", exact: true })
    .click();
  await expect(page.locator("article")).toContainText("alice@example.test");
  await page.getByLabel("Language").selectOption("fr");
  await expect(
    page.getByRole("heading", { name: "Membres de la famille" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Clair", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: "../../data/mobile.png", fullPage: true });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page
    .getByRole("button", { name: "Se déconnecter", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Se connecter" }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});
