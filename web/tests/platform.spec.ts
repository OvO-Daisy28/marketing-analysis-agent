import { test, expect } from "@playwright/test";

test("report generation, sandbox rendering, revision and publication", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("./");
  await page.getByRole("button", { name: "创建自己的分析" }).click();
  await page
    .getByLabel("用户名", { exact: true })
    .fill("browser-" + Date.now());
  await page.getByLabel("密码", { exact: true }).fill("browser-test-password");
  await page.getByRole("button", { name: "创建并进入工作台" }).click();
  await expect(
    page.getByRole("heading", { name: "从一个问题，开始分析。" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "直接生成报表" }).click();
  await page.getByLabel("分析需求").fill("生成11月按流量类型分组的转化率报表");
  await page.getByRole("button", { name: "开始分析" }).click();
  await page
    .getByRole("button", { name: "打开报告草稿" })
    .first()
    .click({ timeout: 75000 });
  const frame = page.frameLocator('iframe[title="报表预览"]');
  await expect(frame.locator("#summary")).toContainText("会话");
  await expect(frame.locator("canvas")).toBeVisible();
  await expect(frame.locator("#chart")).not.toContainText("渲染失败");
  expect(await page.locator("iframe").getAttribute("sandbox")).toBe(
    "allow-scripts",
  );
  await page.getByLabel("报告标题").fill("测试修改后的报告");
  await page.getByRole("button", { name: "保存修改为新版本" }).click();
  await expect(frame.locator("#title")).toHaveText("测试修改后的报告");

  await page.getByRole("button", { name: "确认发布此版本" }).click();
  await expect(
    page.getByRole("button", { name: "已确认发布", exact: true }),
  ).toBeDisabled();
  await expect(frame.locator("#title")).toHaveText("测试修改后的报告");
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "下载离线报告" }).click();
  expect((await download).suggestedFilename()).toMatch(/\.html$/);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page
    .locator("iframe")
    .evaluate((el: any) =>
      el.contentWindow?.postMessage({ type: "scroll-top" }, "*"),
    );
  await page.screenshot({
    path: "test-results/report-published.png",
    fullPage: true,
  });
  await page.getByLabel("筛选月份").selectOption("Dec");
  await page.getByRole("button", { name: "保存修改为新版本" }).click();
  await expect(page.locator(".warning")).toContainText("旧结论已移除");
  await expect(frame.locator("#claims")).toContainText("旧结论已移除");
  await page.getByLabel("展示形式", { exact: true }).selectOption("table");
  await page.getByRole("button", { name: "保存修改为新版本" }).click();
  await expect(frame.locator("table")).toBeVisible();
  await page.getByLabel("展示形式", { exact: true }).selectOption("line");
  await page.getByRole("button", { name: "保存修改为新版本" }).click();
  await expect(frame.locator("canvas")).toBeVisible();
  expect(errors).toEqual([]);
});

test("mobile login has no horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("./");
  await page.getByRole("button", { name: "创建自己的分析" }).click();
  await expect(
    page.getByRole("heading", { name: "创建工作区", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await page.screenshot({ path: "test-results/mobile-login.png" });
});

test("public showcase, evidence drilldown, download and mobile", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("./");
  await expect(page.getByRole("heading", { name: /从流量差异/ })).toBeVisible();
  const frame = page.frameLocator('iframe[title="报表预览"]');
  await expect(frame.locator("canvas")).toBeVisible();
  await page.getByRole("tab", { name: "结论与依据" }).click();
  await page.getByRole("button", { name: "核对证据" }).first().click();
  await expect(page.getByRole("dialog")).toContainText("新访客");
  await expect(page.getByRole("dialog")).toContainText("回访者");
  await page.getByLabel("搜索证据分组").fill("新访客");
  await expect(page.getByRole("dialog").locator("tbody tr")).toHaveCount(1);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("tab", { name: "报告预览" }).click();
  await frame.getByRole("button", { name: "核对证据" }).first().click();
  await expect(page.getByRole("dialog")).toContainText("查询证据");
  await page.getByRole("button", { name: "关闭证据" }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "下载离线报告" }).click();
  expect((await download).suggestedFilename()).toBe("sample-report.html");
  await page.screenshot({
    path: "test-results/showcase-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator("iframe").scrollIntoViewIfNeeded();
  await expect(frame.locator("canvas")).toBeVisible();
  await expect(frame.locator("#title")).toContainText("11 月流量");
  await expect
    .poll(async () =>
      frame
        .locator("canvas")
        .evaluate(
          (el) =>
            el.getBoundingClientRect().width <=
            el.closest("#chart")!.clientWidth + 2,
        ),
    )
    .toBe(true);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await page.screenshot({
    path: "test-results/showcase-mobile.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
