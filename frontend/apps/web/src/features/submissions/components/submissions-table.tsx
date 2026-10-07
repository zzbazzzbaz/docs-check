import type { components } from "@repo/api-client";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@repo/ui/components/table";
import { useNavigate } from "@tanstack/react-router";

import { formatDateTime } from "@/lib/format";
import { CountsSummary } from "./counts-summary";
import { StatusBadge } from "./status-badge";

type SubmissionListItem = components["schemas"]["SubmissionListItem"];

/** 提交列表表格：学生「我的提交」与教师「学生的提交」共用（行点击进详情）。 */
export function SubmissionsTable({ items }: { items: SubmissionListItem[] }) {
  const navigate = useNavigate();

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>提交时间</TableHead>
          <TableHead>原始文件名</TableHead>
          <TableHead>问题统计</TableHead>
          <TableHead>状态</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((item) => (
          <TableRow
            key={item.id}
            className="cursor-pointer"
            onClick={() =>
              void navigate({
                to: "/submissions/$submissionId",
                params: { submissionId: String(item.id) },
              })
            }
          >
            <TableCell className="whitespace-nowrap">{formatDateTime(item.created_at)}</TableCell>
            <TableCell className="max-w-72 truncate" title={item.original_filename}>
              {item.original_filename}
            </TableCell>
            <TableCell>
              {item.status === "success" ? (
                <CountsSummary counts={item.counts} />
              ) : (
                <span className="text-muted-foreground">—</span>
              )}
            </TableCell>
            <TableCell>
              <StatusBadge status={item.status} counts={item.counts} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
