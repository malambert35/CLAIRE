import { expect, test } from "@playwright/test";

test("original photo and PDF survive reload, sharing, trash and downloads", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.getByLabel("Email", { exact: true }).fill("alice@example.test");
  await page
    .getByLabel("Password", { exact: true })
    .fill("synthetic-browser-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page
    .getByRole("button", { name: "Photos and Media", exact: true })
    .click();
  await page.getByRole("button", { name: "Import file", exact: true }).click();
  const png = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jWZkAAAAASUVORK5CYII=",
    "base64",
  );
  await page
    .getByLabel("Original file", { exact: true })
    .setInputFiles({ name: "family.png", mimeType: "image/png", buffer: png });
  await page.getByLabel("File title", { exact: true }).fill("Family photo");
  await page
    .getByLabel("Description", { exact: true })
    .fill("Synthetic photo for browser verification");
  await expect(
    page.getByRole("button", { name: "Save file", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("combobox", { name: "File visibility", exact: true }),
  ).toHaveValue("private");
  await page
    .getByRole("checkbox", { name: "I confirm this file and its visibility." })
    .check();
  await page.getByRole("button", { name: "Save file", exact: true }).click();
  await expect(page.getByText("File saved.", { exact: true })).toBeVisible();
  await expect(page.getByRole("img", { name: "Family photo" })).toBeVisible();
  expect(
    await page
      .getByRole("img", { name: "Family photo" })
      .evaluate((img: HTMLImageElement) => img.naturalWidth),
  ).toBe(1);
  const downloadEvent = page.waitForEvent("download");
  await page
    .getByRole("link", { name: "Download original", exact: true })
    .click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toBe("family.png");
  expect(await download.failure()).toBeNull();
  await page
    .getByRole("button", { name: "Share with family", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Confirm file change", exact: true })
    .click();
  await expect(page.getByText("My family", { exact: true })).toBeVisible();
  await page.reload();
  await page
    .getByRole("button", { name: "Photos and Media", exact: true })
    .click();
  await page.getByRole("button", { name: /Family photo/ }).click();
  await page
    .getByRole("button", { name: "Move file to trash", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Confirm file change", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Restore file", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Back to files", exact: true })
    .click();
  await expect(page.getByRole("button", { name: /Family photo/ })).toHaveCount(
    0,
  );
  await page
    .getByRole("button", { name: "Deleted files", exact: true })
    .click();
  await page.getByRole("button", { name: /Family photo/ }).click();
  await page.getByRole("button", { name: "Restore file", exact: true }).click();
  await page
    .getByRole("button", { name: "Confirm file change", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Move file to trash", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Back to files", exact: true })
    .click();
  await page.getByRole("button", { name: "Import file", exact: true }).click();
  const wav = Buffer.alloc(16044);
  wav.write("RIFF", 0);
  wav.writeUInt32LE(16036, 4);
  wav.write("WAVEfmt ", 8);
  wav.writeUInt32LE(16, 16);
  wav.writeUInt16LE(1, 20);
  wav.writeUInt16LE(1, 22);
  wav.writeUInt32LE(8000, 24);
  wav.writeUInt32LE(16000, 28);
  wav.writeUInt16LE(2, 32);
  wav.writeUInt16LE(16, 34);
  wav.write("data", 36);
  wav.writeUInt32LE(16000, 40);
  await page
    .getByLabel("Original file", { exact: true })
    .setInputFiles({ name: "voice.wav", mimeType: "audio/wav", buffer: wav });
  await page
    .getByRole("checkbox", { name: "I confirm this file and its visibility." })
    .check();
  await page.getByRole("button", { name: "Save file", exact: true }).click();
  await expect(page.locator("audio")).toBeVisible();
  await expect
    .poll(() =>
      page
        .locator("audio")
        .evaluate((audio: HTMLAudioElement) => audio.duration),
    )
    .toBe(1);
  await page
    .locator("audio")
    .evaluate((audio: HTMLAudioElement) => audio.play());
  await expect
    .poll(() =>
      page
        .locator("audio")
        .evaluate((audio: HTMLAudioElement) => audio.currentTime),
    )
    .toBeGreaterThan(0);
  await page
    .getByRole("button", { name: "Documents and Archives", exact: true })
    .click();
  await page
    .getByRole("button", { name: "PDF originals", exact: true })
    .click();
  const pdfLibrary = page.getByRole("region", {
    name: "PDF files",
    exact: true,
  });
  await pdfLibrary
    .getByRole("button", { name: "Import file", exact: true })
    .click();
  await pdfLibrary.getByLabel("Original file", { exact: true }).setInputFiles({
    name: "letter.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.7\n% Synthetic original\n%%EOF"),
  });
  await pdfLibrary
    .getByRole("checkbox", { name: "I confirm this file and its visibility." })
    .check();
  await pdfLibrary
    .getByRole("button", { name: "Save file", exact: true })
    .click();
  await expect(
    pdfLibrary.getByText("File saved.", { exact: true }),
  ).toBeVisible();
  const pdfDownload = page.waitForEvent("download");
  await pdfLibrary
    .getByRole("link", { name: "Download original", exact: true })
    .click();
  expect((await pdfDownload).suggestedFilename()).toBe("letter.pdf");
  await page.getByLabel("Language").selectOption("fr");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: `${process.env.TEMP || "/tmp"}/claire-files-mobile.png`,
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  expect(errors).toEqual([]);
});
