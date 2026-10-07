import { expect, test } from "@playwright/test";

import {
  ADMIN_BASE,
  ADMIN_PASSWORD,
  ADMIN_USERNAME,
  API_BASE,
  loginViaUi,
  WEB_BASE,
} from "./helpers";

test("管理端：建号/编辑/禁用/重置/教师提示/仪表盘", async ({ page, request, browser }) => {
  test.setTimeout(180_000);

  await loginViaUi(page, ADMIN_BASE, ADMIN_USERNAME, ADMIN_PASSWORD);
  await expect(page).toHaveURL(`${ADMIN_BASE}/`);
  await expect(page.getByRole("heading", { name: "仪表盘" })).toBeVisible();

  const search = page.getByPlaceholder("搜索账号 / 姓名");

  // 教师 tab 建教师
  await page.goto(`${ADMIN_BASE}/users`);
  await page.getByRole("tab", { name: "教师" }).click();
  await page.getByRole("button", { name: "新建教师" }).click();
  let dialog = page.getByRole("dialog");
  const teacherUsername = `t${Date.now().toString(36)}`;
  await dialog.getByLabel("工号").fill(teacherUsername);
  await dialog.getByLabel("姓名").fill("界面教师");
  await dialog.getByRole("button", { name: "保存" }).click();
  await expect(page.getByText("账号已创建，初始密码 123456")).toBeVisible();

  await search.fill(teacherUsername);
  const teacherRow = page.getByRole("row", { name: new RegExp(teacherUsername) });
  await expect(teacherRow).toBeVisible();
  await expect(teacherRow.getByRole("cell", { name: "0", exact: true })).toBeVisible();

  // 学生 tab 建学生并指定教师
  await page.getByRole("tab", { name: "学生" }).click();
  await search.fill("");
  await page.getByRole("button", { name: "新建学生" }).click();
  dialog = page.getByRole("dialog");
  const studentUsername = `s${Date.now().toString(36)}`;
  await dialog.getByLabel("学号").fill(studentUsername);
  await dialog.getByLabel("姓名").fill("界面学生");
  await dialog.getByLabel("专业（可空）").fill("网络工程");
  await dialog.getByRole("combobox").click();
  await page.getByRole("option", { name: new RegExp(teacherUsername) }).click();
  await dialog.getByRole("button", { name: "保存" }).click();
  await expect(page.getByText("账号已创建，初始密码 123456")).toBeVisible();

  await search.fill(studentUsername);
  const studentRow = page.getByRole("row", { name: new RegExp(studentUsername) });
  await expect(studentRow).toBeVisible();
  await expect(studentRow.getByText("网络工程")).toBeVisible();
  await expect(studentRow.getByText("界面教师")).toBeVisible();

  // 编辑：改姓名
  await studentRow.getByRole("button", { name: "操作" }).click();
  await page.getByRole("menuitem", { name: "编辑" }).click();
  dialog = page.getByRole("dialog");
  await dialog.getByLabel("姓名").fill("界面学生改");
  await dialog.getByRole("button", { name: "保存" }).click();
  await expect(page.getByText("已保存")).toBeVisible();
  await expect(studentRow.getByRole("cell", { name: "界面学生改" })).toBeVisible();

  // 禁用学生 → API 403 + UI 提示；再启用
  await studentRow.getByRole("button", { name: "操作" }).click();
  await page.getByRole("menuitem", { name: "禁用" }).click();
  const alert = page.getByRole("alertdialog");
  await expect(alert.getByText(/将无法登录/)).toBeVisible();
  await alert.getByRole("button", { name: "禁用" }).click();
  await expect(page.getByText("已禁用", { exact: true })).toBeVisible();
  const disabledLogin = await request.post(`${API_BASE}/api/v1/auth/login`, {
    data: { username: studentUsername, password: "123456" },
  });
  expect(disabledLogin.status()).toBe(403);

  const blockedContext = await browser.newContext();
  const blockedPage = await blockedContext.newPage();
  await loginViaUi(blockedPage, WEB_BASE, studentUsername, "123456");
  await expect(blockedPage.getByText("账号已被禁用，请联系管理员")).toBeVisible();
  await blockedContext.close();

  await studentRow.getByRole("button", { name: "操作" }).click();
  await page.getByRole("menuitem", { name: "启用" }).click();
  await alert.getByRole("button", { name: "启用" }).click();
  await expect(page.getByText("已启用", { exact: true })).toBeVisible();

  // 重置密码 → 初始密码可登录且强制改密
  await studentRow.getByRole("button", { name: "操作" }).click();
  await page.getByRole("menuitem", { name: "重置密码" }).click();
  await expect(alert.getByText(/重置为初始密码 123456/)).toBeVisible();
  await alert.getByRole("button", { name: "重置" }).click();
  await expect(page.getByText("已重置为初始密码 123456")).toBeVisible();

  const login = await request.post(`${API_BASE}/api/v1/auth/login`, {
    data: { username: studentUsername, password: "123456" },
  });
  expect(login.ok()).toBeTruthy();
  const token = ((await login.json()) as { access_token: string }).access_token;
  const me = await request.get(`${API_BASE}/api/v1/users/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(((await me.json()) as { must_change_password: boolean }).must_change_password).toBe(true);

  // 教师 tab：名下学生数 + 禁用提示
  await page.getByRole("tab", { name: "教师" }).click();
  await search.fill(teacherUsername);
  const teacherRow2 = page.getByRole("row", { name: new RegExp(teacherUsername) });
  await expect(teacherRow2.getByRole("cell", { name: "1", exact: true })).toBeVisible();
  await teacherRow2.getByRole("button", { name: "操作" }).click();
  await page.getByRole("menuitem", { name: "禁用" }).click();
  await expect(page.getByRole("alertdialog").getByText(/名下还有 1 名学生/)).toBeVisible();
  await page.getByRole("alertdialog").getByRole("button", { name: "取消" }).click();

  // 仪表盘快捷入口（预设教师 tab）与计数
  await page.goto(`${ADMIN_BASE}/`);
  await expect(page.getByText("提交数（全部）")).toBeVisible();
  await page.getByRole("link", { name: "前往教师管理" }).click();
  await expect(page).toHaveURL(`${ADMIN_BASE}/users?role=teacher`);
  await expect(page.getByRole("tab", { name: "教师", selected: true })).toBeVisible();
});
