import { expect, test } from "@playwright/test";

import { createReadyUser, createUserViaApi, loginViaUi, WEB_BASE } from "./helpers";

test("密码错误提示后端错误文案", async ({ page, request }) => {
  const user = await createUserViaApi(request, { role: "student" });

  await loginViaUi(page, WEB_BASE, user.username, "wrong-password");

  await expect(page.getByText("账号或密码错误")).toBeVisible();
  await expect(page).toHaveURL(`${WEB_BASE}/login`);
});

test("学生登录后进入我的提交", async ({ page, request }) => {
  const user = await createReadyUser(request, { role: "student", name: "登录测试" });

  await loginViaUi(page, WEB_BASE, user.username, user.password);

  await expect(page).toHaveURL(`${WEB_BASE}/`);
  await expect(page.getByRole("heading", { name: "我的提交" })).toBeVisible();
});
