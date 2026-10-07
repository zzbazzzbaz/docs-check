import type { components } from "@repo/api-client";

import { type Counts, totalCount } from "./status";

type SubmissionListItem = components["schemas"]["SubmissionListItem"];

/** 趋势图上的一个点（一次成功提交）。 */
export interface TrendPoint {
  /** 第 N 次提交：该生全部提交按时间正序编号（含失败），与详情页口径一致。 */
  sequence: number;
  createdAt: string;
  filename: string;
  counts: Counts;
  total: number;
}

/** 每生最多展示的最近成功提交数（与后端 `/students/stats` 截断口径一致）。 */
export const TREND_POINT_LIMIT = 50;

/**
 * 从倒序提交列表构建趋势点：只取成功提交、按时间正序、最多最近 50 个。
 * `total` 为全部提交数（含失败），用于推导「第 N 次提交」。
 */
export function buildTrendPoints(items: SubmissionListItem[], total: number): TrendPoint[] {
  return items
    .flatMap((item, index): TrendPoint[] =>
      item.status === "success"
        ? [
            {
              sequence: total - index,
              createdAt: item.created_at,
              filename: item.original_filename,
              counts: item.counts,
              total: totalCount(item.counts),
            },
          ]
        : [],
    )
    .reverse()
    .slice(-TREND_POINT_LIMIT);
}
