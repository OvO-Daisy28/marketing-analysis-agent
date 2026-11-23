import { test, expect } from "@playwright/test";

test("API documentation renders with external network blocked", async ({ page, baseURL }) => {
  const externalRequests: string[] = [];
  const origin = new URL(baseURL!).origin;
  await page.route("**/*", async (route) => {
    if (new URL(route.request().url()).origin !== origin) {
      externalRequests.push(route.request().url());
      await route.abort();
    } else {
      await route.continue();
    }
  });
  await page.goto("/docs");
  await expect(page.locator(".swagger-ui .info .title")).toContainText("Marketing Analysis Agent");
  await expect(page.locator("#operations-default-health_api_health_get")).toBeVisible();
  expect(await page.locator(".opblock").count()).toBeGreaterThan(10);
  expect(externalRequests).toEqual([]);
  await page.screenshot({ path: "test-results/api-docs.png", fullPage: true });
});

test("workbench entry loads", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: "创建自己的分析" })).toBeVisible();
  await page.getByRole("button", { name: "创建自己的分析" }).click();
  await expect(page.getByLabel("用户名", { exact: true })).toBeVisible();
  await expect(page.getByText("公开复现项目", { exact: false })).toHaveCount(0);
});
