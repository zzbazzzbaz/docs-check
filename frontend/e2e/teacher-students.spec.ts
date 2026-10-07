import { expect, test } from "@playwright/test";

import { createReadyUser, loginViaUi, WEB_BASE } from "./helpers";

test("教师看到名下学生并显示空态字段", async ({ page, request }) => {
  const teacher = await createReadyUser(request, { role: "teacher", name: "教师用例" });
  const student = await createReadyUser(request, {
    role: "student",
    name: "教师用例学生",
    major: "计算机科学与技术",
    teacherId: teacher.id,
  });

  await loginViaUi(page, WEB_BASE, teacher.username, teacher.password);

  await expect(page).toHaveURL(`${WEB_BASE}/students`);
  await expect(page.getByRole("heading", { name: "我的学生" })).toBeVisible();

  // 统计概览：卡片数值 + 趋势图空态（该生暂无成功提交）
  const statsCards = page.locator("[data-slot=card]");
  await expect(
    statsCards.filter({ hasText: "名下学生数" }).getByText("1", { exact: true }),
  ).toBeVisible();
  await expect(
    statsCards.filter({ hasText: "提交过的学生数" }).getByText("0", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("学生历史趋势（总问题）")).toBeVisible();
  await expect(page.getByText("名下学生暂无成功审核记录")).toBeVisible();

  const row = page.getByRole("row", { name: new RegExp(student.username) });
  await expect(row).toBeVisible();
  await expect(row.getByText("计算机科学与技术")).toBeVisible();
  await expect(row.getByText("—").first()).toBeVisible();
});

test("学生访问教师页会被重定向回首页", async ({ page, request }) => {
  const student = await createReadyUser(request, { role: "student", name: "重定向用例" });

  await loginViaUi(page, WEB_BASE, student.username, student.password);
  await expect(page).toHaveURL(`${WEB_BASE}/`);

  await page.goto(`${WEB_BASE}/students`);
  await expect(page).toHaveURL(`${WEB_BASE}/`);
});
