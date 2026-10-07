import { Badge } from "@repo/ui/components/badge";

import { type Counts, type SubmissionStatus, totalCount } from "../lib/status";

/** 状态徽章：排队中/审核中（灰）、审核失败/存在问题（红）、全部通过（绿）。 */
export function StatusBadge({ status, counts }: { status: SubmissionStatus; counts: Counts }) {
  if (status === "pending") {
    return <Badge variant="secondary">排队中</Badge>;
  }
  if (status === "processing") {
    return <Badge variant="secondary">审核中</Badge>;
  }
  if (status === "failed") {
    return <Badge variant="destructive">审核失败</Badge>;
  }
  if (totalCount(counts) === 0) {
    return <Badge>全部通过</Badge>;
  }
  return <Badge variant="destructive">存在问题（{counts.fail}）</Badge>;
}
