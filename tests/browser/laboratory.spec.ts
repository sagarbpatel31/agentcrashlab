import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";

test("campaign → committed effect → replay → isolated repair → exported bundle", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Find the failure. Prove the fix.",
  );
  await expect(
    page.getByRole("combobox", { name: "Target agent" }),
  ).toHaveValue("workspace");
  const campaign = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/lab/campaigns") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Run campaign" }).click();
  expect((await campaign).status()).toBe(202);
  await expect(page.getByRole("button", { name: "Run campaign" })).toBeEnabled({
    timeout: 30000,
  });
  const failureRow = page
    .locator("tbody tr")
    .filter({ hasText: "Response lost after commit" })
    .filter({ hasText: "Scripted fixture" })
    .filter({ hasText: "Failed" })
    .first();
  await failureRow.getByRole("button").first().click();
  await expect(
    page.getByText("Expected 1 workspace; observed 2"),
  ).toBeVisible();
  await expect(page.getByText("OBSERVATION ≠ REALITY").first()).toBeVisible();
  await page.getByRole("button", { name: "Replay recorded actions" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Replay verified" }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Repair", exact: true }).click();
  await page.getByRole("button", { name: "Import candidate source" }).click();
  const source = readFileSync("examples/workspace/agent.py", "utf8").replace(
    'f"{key}:{attempt}"',
    "key",
  );
  await page
    .getByRole("textbox", { name: "Replacement agent.py" })
    .fill(source);
  await page
    .getByRole("button", { name: "Save candidate for verification" })
    .click();
  await expect(
    page.getByText("candidate.patch", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Isolation runner").selectOption("docker");
  await page.getByRole("button", { name: "Verify in Docker" }).click();
  await expect(page.locator(".patch-title .status")).toHaveText("verified", {
    timeout: 90000,
  });
  await expect(page.locator(".verification-matrix .status.pass")).toHaveCount(
    4,
  );
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Export repair bundle" }).click();
  expect((await download).suggestedFilename()).toBe(
    "agentcrashlab-evidence.zip",
  );
  await page.screenshot({
    path: ".agentcrashlab/screenshots/verified-repair.png",
    fullPage: true,
  });
});

test("second agent, connection status and malformed experiment validation", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByRole("combobox", { name: "Target agent" })
    .selectOption("publisher");
  await page.getByRole("button", { name: "Review experiments" }).click();
  await page
    .getByRole("textbox", { name: "Experiment JSON" })
    .fill(
      '[{"name":"invalid","faults":[{"kind":"stale_read","tool":"publish_artifact","occurrence":1}]}]',
    );
  await page.getByRole("button", { name: "Apply specification" }).click();
  await page.getByRole("button", { name: "Run campaign" }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "incompatible" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Connections", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Meta Model API", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Isolated execution", exact: true }),
  ).toBeVisible();
});
