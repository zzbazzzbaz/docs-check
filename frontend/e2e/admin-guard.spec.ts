import { expect, test } from "@playwright/test";

import { ADMIN_BASE, ADMIN_PASSWORD, ADMIN_USERNAME, createReadyUser, loginViaUi } from "./helpers";

test("未登录访问后台会跳到登录页", async ({ page }) => {
  await page.goto(`${ADMIN_BASE}/users`);
  await expect(page).toHaveURL(`${ADMIN_BASE}/login`);
  await expect(page.getByText("登录管理后台")).toBeVisible();
});

test("学生账号登录后台会被拒绝", async ({ page, request }) => {
  const user = await createReadyUser(request, { role: "student" });

  await loginViaUi(page, ADMIN_BASE, user.username, user.password);

  await expect(page.getByRole("heading", { name: "无权访问" })).toBeVisible();
});

test("管理员登录后进入仪表盘", async ({ page }) => {
  await loginViaUi(page, ADMIN_BASE, ADMIN_USERNAME, ADMIN_PASSWORD);

  await expect(page).toHaveURL(`${ADMIN_BASE}/`);
  await expect(page.getByRole("heading", { name: "仪表盘" })).toBeVisible();
});
