import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests/browser",
  timeout: 120000,
  workers: 1,
  webServer: {
    command: "npm run dev",
    url: "http://127.0.0.1:3000/api/lab/bootstrap",
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
  },
  use: {
    baseURL: "http://127.0.0.1:3000",
    viewport: { width: 1440, height: 1080 },
    video: "on",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  reporter: [["list"], ["html", { open: "never" }]],
});
