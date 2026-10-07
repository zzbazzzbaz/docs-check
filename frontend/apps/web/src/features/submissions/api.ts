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

export function uploadSubmission(file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return unwrap(
    api.POST("/api/v1/submissions", {
      // openapi-fetch 默认 bodySerializer 对 FormData 原样透传，浏览器自动带 multipart boundary
      body: formData as unknown as { file: string },
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
