import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/browser",
  fullyParallel: true,
  timeout: 20_000,
  expect: {
    timeout: 3_000,
  },
  projects: [
    {
      name: "chromium",
      use: {
        headless: true,
        trace: "off",
      },
    },
  ],
  reporter: [["line"]],
});
