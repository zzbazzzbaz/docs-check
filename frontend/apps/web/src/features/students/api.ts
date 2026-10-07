import { queryOptions } from "@tanstack/react-query";

import { isTerminal } from "@/features/submissions/lib/status";
import { api, unwrap } from "@/lib/api";

const POLL_INTERVAL_MS = 2000;

export const studentsQueryOptions = (q: string, offset: number, limit: number) =>
  queryOptions({
    queryKey: ["students", { q, offset, limit }],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/students", {
          params: { query: { q: q || undefined, offset, limit } },
        }),
      ),
  });

/** 教师概览：名下学生数 / 提交过的学生数 / 每生最近 50 次成功提交序列。 */
export const studentsStatsQueryOptions = () =>
  queryOptions({
    queryKey: ["students-stats"],
    queryFn: () => unwrap(api.GET("/api/v1/students/stats")),
  });

export const studentQueryOptions = (studentId: number) =>
  queryOptions({
    queryKey: ["student", studentId],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/students/{student_id}", {
          params: { path: { student_id: studentId } },
        }),
      ),
  });

export const studentSubmissionsQueryOptions = (studentId: number, offset: number, limit: number) =>
  queryOptions({
    queryKey: ["student-submissions", studentId, { offset, limit }],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/students/{student_id}/submissions", {
          params: { path: { student_id: studentId }, query: { offset, limit } },
        }),
      ),
    // 该生仍有排队中/审核中的提交时轮询
    refetchInterval: (query) =>
      (query.state.data?.items ?? []).some((item) => !isTerminal(item.status))
        ? POLL_INTERVAL_MS
        : false,
  });

/** 教师学生详情趋势数据源（上限 100 条，前端再截断最近 50 个成功点）。 */
export const studentTrendQueryOptions = (studentId: number) =>
  queryOptions({
    queryKey: ["student-submissions-trend", studentId],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/students/{student_id}/submissions", {
          params: { path: { student_id: studentId }, query: { offset: 0, limit: 100 } },
        }),
      ),
    // 与提交列表同一规则：存在非终态时轮询
    refetchInterval: (query) =>
      (query.state.data?.items ?? []).some((item) => !isTerminal(item.status))
        ? POLL_INTERVAL_MS
        : false,
  });
