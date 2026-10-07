import { queryOptions } from "@tanstack/react-query";
import { isTerminal } from "@/features/submissions/lib/status";
import { ApiError, api, errorCode, errorMessage, unwrap } from "@/lib/api";

const POLL_INTERVAL_MS = 2000;

export const submissionsQueryOptions = (offset: number, limit: number) =>
  queryOptions({
    queryKey: ["submissions", { offset, limit }],
    queryFn: () => unwrap(api.GET("/api/v1/submissions", { params: { query: { offset, limit } } })),
    // 存在排队中/审核中的条目时轮询，等待 worker 出结果
    refetchInterval: (query) =>
      (query.state.data?.items ?? []).some((item) => !isTerminal(item.status))
        ? POLL_INTERVAL_MS
        : false,
  });

/** 学生端趋势/提交次数数据源（上限 100 条；只用于顶部统计区，列表分页另走 submissionsQueryOptions）。 */
export const submissionTrendQueryOptions = () =>
  queryOptions({
    queryKey: ["submissions-trend"],
    queryFn: () =>
      unwrap(api.GET("/api/v1/submissions", { params: { query: { offset: 0, limit: 100 } } })),
    refetchInterval: (query) =>
      (query.state.data?.items ?? []).some((item) => !isTerminal(item.status))
        ? POLL_INTERVAL_MS
        : false,
  });

export const submissionQueryOptions = (submissionId: number) =>
  queryOptions({
    queryKey: ["submission", submissionId],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/submissions/{submission_id}", {
          params: { path: { submission_id: submissionId } },
        }),
      ),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status !== undefined && !isTerminal(status) ? POLL_INTERVAL_MS : false;
    },
  });

/** 签发预签名上传 URL（三段式 ①）。 */
function signUpload(file: File) {
  return unwrap(
    api.POST("/api/v1/submissions/upload-url", {
      body: { filename: file.name, size: file.size },
    }),
  );
}

/** 直传 COS（三段式 ②）；网络异常也转成可展示的 ApiError。 */
async function putToCos(url: string, file: File): Promise<Response> {
  try {
    return await fetch(url, { method: "PUT", body: file });
  } catch {
    throw new ApiError(0, "网络异常，文件上传失败，请重试");
  }
}

/**
 * 上传三段式：签发预签名 PUT → 直传 COS（字节不经过后端）→ 确认入队。
 * 直传 401 / 403（预签名过期）时重新签发并重试一次；其余失败抛中文提示。
 */
export async function uploadSubmission(file: File) {
  let signed = await signUpload(file);
  let response = await putToCos(signed.upload_url, file);
  if (!response.ok && (response.status === 401 || response.status === 403)) {
    signed = await signUpload(file);
    response = await putToCos(signed.upload_url, file);
  }
  if (!response.ok) {
    throw new ApiError(response.status, "文件上传失败，请重试");
  }
  return unwrap(
    api.POST("/api/v1/submissions", {
      body: { object_key: signed.object_key, filename: file.name },
    }),
  );
}

function filenameFromDisposition(header: string | null): string | null {
  if (!header) {
    return null;
  }
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (encoded?.[1]) {
    return decodeURIComponent(encoded[1]);
  }
  const plain = /filename="?([^";]+)"?/i.exec(header);
  return plain?.[1] ?? null;
}

function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

/** 带 token 下载原始/标注文件；文件名优先取 Content-Disposition（中文走 filename*）。 */
export async function downloadSubmissionFile(
  submissionId: number,
  kind: "original" | "marked",
  fallbackName: string,
): Promise<void> {
  const result =
    kind === "original"
      ? await api.GET("/api/v1/submissions/{submission_id}/original", {
          params: { path: { submission_id: submissionId } },
          parseAs: "blob",
        })
      : await api.GET("/api/v1/submissions/{submission_id}/marked", {
          params: { path: { submission_id: submissionId } },
          parseAs: "blob",
        });

  if (result.error !== undefined) {
    throw new ApiError(result.response.status, errorMessage(result.error), errorCode(result.error));
  }
  const filename =
    filenameFromDisposition(result.response.headers.get("content-disposition")) ?? fallbackName;
  saveBlob(result.data, filename);
}
