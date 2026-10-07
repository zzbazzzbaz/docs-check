import { queryOptions } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api";

/** 仪表盘统计（启用学生数 / 启用教师数 / 全部提交数）。 */
export const adminStatsQueryOptions = queryOptions({
  queryKey: ["admin-stats"],
  queryFn: () => unwrap(api.GET("/api/v1/admin/stats")),
});
