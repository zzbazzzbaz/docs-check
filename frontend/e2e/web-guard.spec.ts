import { expect, test } from "@playwright/test";

import { WEB_BASE } from "./helpers";

test("未登录访问首页会跳到登录页", async ({ page }) => {
  await page.goto(`${WEB_BASE}/`);
  await expect(page).toHaveURL(`${WEB_BASE}/login`);
  await expect(page.getByRole("button", { name: "登录", exact: true })).toBeVisible();
});

test("token 失效后自动回到登录页", async ({ page }) => {
  await page.goto(`${WEB_BASE}/login`);
  await page.evaluate(() => localStorage.setItem("auth_token", "invalid-token"));
  await page.goto(`${WEB_BASE}/`);
  await expect(page).toHaveURL(`${WEB_BASE}/login`);
});
