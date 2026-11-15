import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  use: {
    baseURL: "http://127.0.0.1:8010",
    viewport: { width: 1440, height: 1000 },
  },
  outputDir: "../../data/browser-results",
});
