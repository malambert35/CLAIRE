import { expect, test } from "@playwright/test";

test("administrator configures MCP, secret stays hidden and connection errors are visible", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.getByLabel("Email", { exact: true }).fill("admin@example.test");
  await page
    .getByLabel("Password", { exact: true })
    .fill("synthetic-browser-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("button", { name: "Integrations", exact: true }).click();
  await page
    .getByLabel("MCP server address", { exact: true })
    .fill("http://127.0.0.1:5000/mcp");
  await page
    .getByLabel("MCP proxy Bearer token (optional)", { exact: true })
    .fill("synthetic-browser-token");
  await page
    .getByRole("checkbox", { name: "Enable Immich connection", exact: true })
    .check();
  await expect(
    page.getByRole("button", { name: "Save connection", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("checkbox", {
      name: "I confirm this server and access to its library.",
      exact: true,
    })
    .check();
  await page
    .getByRole("button", { name: "Save connection", exact: true })
    .click();
  await expect(
    page.getByText("Configuration saved.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByLabel("MCP proxy Bearer token (optional)", { exact: true }),
  ).toHaveValue("");
  await page.reload();
  await page.getByRole("button", { name: "Integrations", exact: true }).click();
  await expect(
    page.getByLabel("MCP server address", { exact: true }),
  ).toHaveValue("http://127.0.0.1:5000/mcp");
  await expect(
    page.getByRole("checkbox", { name: "Remove saved token", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Test connection", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("loopback");
  await page.getByLabel("Language").selectOption("fr");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: `${process.env.TEMP || "/tmp"}/claire-immich-settings.png`,
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page
    .getByRole("button", { name: "Supprimer la connexion", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Confirmer la suppression", exact: true })
    .click();
  await expect(
    page.getByLabel("Adresse du serveur MCP", { exact: true }),
  ).toHaveValue("");
  expect(errors).toEqual([]);
});
