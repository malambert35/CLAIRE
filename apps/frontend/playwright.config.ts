import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  // These workflows share the same disposable household and SQLite server.
  workers: 1,
  use: {
    baseURL: process.env.CLAIRE_BROWSER_ORIGIN || "http://127.0.0.1:8010",
    viewport: { width: 1440, height: 1000 },
  },
  outputDir: "../../data/browser-results",
});
