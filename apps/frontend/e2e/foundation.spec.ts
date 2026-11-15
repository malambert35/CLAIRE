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

test("memory persists through reload, revisions, deletion and restoration", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Email", { exact: true }).fill("alice@example.test");
  await page
    .getByLabel("Password", { exact: true })
    .fill("synthetic-browser-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("button", { name: "New memory", exact: true }).click();
  await page.getByLabel("Title", { exact: true }).fill("The summer of 1962");
  await page
    .getByLabel("Your memory", { exact: true })
    .fill("We made **crêpes** together.");
  await page
    .getByLabel("When did it happen? (optional)", { exact: true })
    .fill("1962-07-14");
  await page
    .getByLabel("Source or witness (optional)", { exact: true })
    .fill("A recorded interview");
  await page
    .getByLabel("I confirm this content and who can read it.", { exact: true })
    .check();
  await page.getByRole("button", { name: "Save memory", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText(
    "Memory saved to the archive.",
  );
  await expect(page.locator(".markdown strong")).toHaveText("crêpes");
  await page.reload();
  await page.getByRole("button", { name: /The summer of 1962/ }).click();
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page
    .getByLabel("Your memory", { exact: true })
    .fill("Correction: it was **1963**.");
  await page
    .getByLabel("I confirm this content and who can read it.", { exact: true })
    .check();
  await page.getByRole("button", { name: "Save memory", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText(
    "Memory saved to the archive.",
  );
  await page
    .getByRole("button", { name: "Revision history", exact: true })
    .click();
  await page.locator("summary").filter({ hasText: "Revision 1" }).click();
  await expect(page.locator(".history")).toContainText(
    "We made crêpes together.",
  );
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download all versions (.zip)", exact: true }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^claire-memory-.*\.zip$/);
  await download.saveAs("../../data/memory-export-smoke.zip");
  expect(await download.failure()).toBeNull();
  await page.screenshot({
    path: "../../data/memory-desktop.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Move to deleted", exact: true })
    .click();
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect(page.getByRole("status")).toContainText(
    "Memory moved to deleted",
  );
  await page
    .getByRole("button", { name: "Recently deleted", exact: true })
    .click();
  await page.getByRole("button", { name: /The summer of 1962/ }).click();
  await page
    .getByRole("button", { name: "Restore memory", exact: true })
    .click();
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText("Memory restored.");
  await page.getByRole("button", { name: "Memories", exact: true }).click();
  await page.getByLabel("Language").selectOption("fr");
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("button", { name: /The summer of 1962/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: /The summer of 1962/ }).click();
  await expect(page.getByRole("button", { name: "Télécharger toutes les versions (.zip)", exact: true })).toBeVisible();
  await page.screenshot({
    path: "../../data/memory-mobile.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Retour aux souvenirs", exact: true }).click();
  await page.getByRole("button", { name: "Importer un souvenir (.zip)", exact: true }).click();
  await page.getByLabel("Fichier ZIP CLAIRE").setInputFiles("../../data/memory-export-smoke.zip");
  await page.getByRole("button", { name: "Vérifier et prévisualiser", exact: true }).click();
  await expect(page.getByText("2 versions · copie privée", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Créer la copie privée", exact: true })).toBeDisabled();
  await page.getByRole("checkbox", { name: /Je confirme la création/ }).check();
  await page.screenshot({ path: "../../data/import-preview-mobile.png", fullPage: true });
  await page.getByRole("button", { name: "Créer la copie privée", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText("Souvenir enregistré dans les archives.");
  await expect(page.locator(".markdown strong")).toHaveText("1963");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
});
