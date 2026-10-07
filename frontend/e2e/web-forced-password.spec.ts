import { expect, test } from "@playwright/test";

import { createUserViaApi, INITIAL_PASSWORD, loginViaUi, WEB_BASE } from "./helpers";

test("首次登录强制修改密码后才能进入系统", async ({ page, request }) => {
  const user = await createUserViaApi(request, { role: "student", name: "改密测试" });
  const newPassword = "changed123";

  // 初始密码登录 → 落在修改密码页
  await loginViaUi(page, WEB_BASE, user.username, INITIAL_PASSWORD);
  await expect(page).toHaveURL(`${WEB_BASE}/change-password`);
  await expect(page.getByRole("button", { name: "确认修改" })).toBeVisible();

  // 直接访问首页也会被门禁拉回
  await page.goto(`${WEB_BASE}/`);
  await expect(page).toHaveURL(`${WEB_BASE}/change-password`);

  // 改密 → 进入系统
  await page.getByLabel("旧密码").fill(INITIAL_PASSWORD);
  await page.getByLabel("新密码", { exact: true }).fill(newPassword);
  await page.getByLabel("确认新密码").fill(newPassword);
  await page.getByRole("button", { name: "确认修改" }).click();

  await expect(page).toHaveURL(`${WEB_BASE}/`);
  await expect(page.getByRole("heading", { name: "我的提交" })).toBeVisible();

  // 退出后新密码可再次登录
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(page).toHaveURL(`${WEB_BASE}/login`);
  await loginViaUi(page, WEB_BASE, user.username, newPassword);
  await expect(page).toHaveURL(`${WEB_BASE}/`);
});
