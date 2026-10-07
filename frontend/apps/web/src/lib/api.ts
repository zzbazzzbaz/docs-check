import { createApiClient } from "@repo/api-client";
import { clearToken, getToken } from "@/features/auth/token";
import { API_BASE_URL } from "@/lib/env";

export const api = createApiClient({
  baseUrl: API_BASE_URL,
  getToken,
  onUnauthorized: () => {
    // 带 token 的请求 401 = 会话失效；整页跳转会重建应用，无需额外清理 QueryCache
    if (getToken() !== null) {
      clearToken();
      window.location.assign("/login");
    }
  },
});

export { ApiError, errorCode, errorMessage, toErrorMessage, unwrap } from "@repo/api-client";
