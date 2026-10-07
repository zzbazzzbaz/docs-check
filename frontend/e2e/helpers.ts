import type { APIRequestContext, Page } from "@playwright/test";

/** 后端与两个前端的地址；管理员账号可用环境变量覆盖（默认与本地开发一致）。 */
export const API_BASE = process.env.E2E_API_BASE_URL ?? "http://localhost:8000";
export const WEB_BASE = "http://localhost:5173";
export const ADMIN_BASE = "http://localhost:5174";
export const ADMIN_USERNAME = process.env.E2E_ADMIN_USERNAME ?? "admin";
export const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "admin123";

/** 管理端新建账号的初始密码（后端 INITIAL_PASSWORD）。 */
export const INITIAL_PASSWORD = "123456";

export interface ApiUser {
  id: number;
  username: string;
}

export interface ReadyUser extends ApiUser {
  /** 经 API 完成首次改密后的最终密码。 */
  password: string;
}

let seq = 0;

function uniqueUsername(prefix: string): string {
  seq += 1;
  return `${prefix}${Date.now().toString(36)}${seq}`;
}

export async function apiLogin(
  request: APIRequestContext,
  username: string,
  password: string,
): Promise<string> {
  const res = await request.post(`${API_BASE}/api/v1/auth/login`, {
    data: { username, password },
  });
  if (!res.ok()) {
    throw new Error(`API 登录失败（${username}）：HTTP ${res.status()} ${await res.text()}`);
  }
  const body = (await res.json()) as { access_token: string };
  return body.access_token;
}

/** 管理端建号（返回初始密码账号，must_change_password=true）。 */
export async function createUserViaApi(
  request: APIRequestContext,
  options: { role: "student" | "teacher"; name?: string; major?: string; teacherId?: number },
): Promise<ApiUser> {
  const adminToken = await apiLogin(request, ADMIN_USERNAME, ADMIN_PASSWORD);
  const username = uniqueUsername(options.role === "student" ? "e2es" : "e2et");
  const data: Record<string, unknown> = {
    role: options.role,
    username,
    name: options.name ?? "端到端测试",
  };
  if (options.role === "student") {
    if (options.major !== undefined) data.major = options.major;
    if (options.teacherId !== undefined) data.teacher_id = options.teacherId;
  }

  const res = await request.post(`${API_BASE}/api/v1/admin/users`, {
    headers: { Authorization: `Bearer ${adminToken}` },
    data,
  });
  if (!res.ok()) {
    throw new Error(`管理端建号失败：HTTP ${res.status()} ${await res.text()}`);
  }
  const created = (await res.json()) as { id: number };
  return { id: created.id, username };
}

/** 建号后走 API 完成首次改密，得到可直接登录 UI 的账号。 */
export async function createReadyUser(
  request: APIRequestContext,
  options: { role: "student" | "teacher"; name?: string; major?: string; teacherId?: number },
): Promise<ReadyUser> {
  const user = await createUserViaApi(request, options);
  const password = "e2ePass123";
  const token = await apiLogin(request, user.username, INITIAL_PASSWORD);
  const res = await request.post(`${API_BASE}/api/v1/users/me/password`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { old_password: INITIAL_PASSWORD, new_password: password },
  });
  if (!res.ok()) {
    throw new Error(`API 首次改密失败：HTTP ${res.status()} ${await res.text()}`);
  }
  return { ...user, password };
}

/** UI 登录（baseUrl 用 WEB_BASE / ADMIN_BASE）。 */
export async function loginViaUi(
  page: Page,
  baseUrl: string,
  username: string,
  password: string,
): Promise<void> {
  await page.goto(`${baseUrl}/login`);
  await page.getByLabel("账号").fill(username);
  await page.getByLabel("密码").fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
}
