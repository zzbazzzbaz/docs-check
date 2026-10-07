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

test("个人信息页展示学生资料与改密入口", async ({ page, request }) => {
  const teacher = await createReadyUser(request, { role: "teacher", name: "资料导师" });
  const student = await createReadyUser(request, {
    role: "student",
    name: "资料学生",
    major: "软件工程",
    teacherId: teacher.id,
  });

  await loginViaUi(page, WEB_BASE, student.username, student.password);
  await expect(page).toHaveURL(`${WEB_BASE}/`);
  await page.getByRole("link", { name: "个人信息" }).click();

  await expect(page).toHaveURL(`${WEB_BASE}/profile`);
  await expect(page.getByRole("heading", { name: "个人信息" })).toBeVisible();
  await expect(page.getByText("资料学生").first()).toBeVisible();
  await expect(page.getByText("软件工程")).toBeVisible();
  await expect(page.getByText("资料导师")).toBeVisible();
  await expect(page.getByText("正常")).toBeVisible();

  await page.getByRole("link", { name: "修改密码" }).click();
  await expect(page).toHaveURL(`${WEB_BASE}/change-password`);
});
