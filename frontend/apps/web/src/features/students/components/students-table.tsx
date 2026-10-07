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

type StudentListItem = components["schemas"]["StudentListItem"];

function latestCountsTitle(student: StudentListItem): string | undefined {
  const counts = student.latest_counts;
  if (!counts) {
    return undefined;
  }
  return `不符合 ${counts.fail} · 无法判定 ${counts.undetermined} · 未执行 ${counts.not_run} · 未识别 ${counts.unrecognised}`;
}

/** 教师「我的学生」列表（行点击进学生详情）。 */
export function StudentsTable({ items }: { items: StudentListItem[] }) {
  const navigate = useNavigate();

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>学号</TableHead>
          <TableHead>姓名</TableHead>
          <TableHead>专业</TableHead>
          <TableHead>提交次数</TableHead>
          <TableHead>最近提交时间</TableHead>
          <TableHead>最新问题数</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((student) => (
          <TableRow
            key={student.id}
            className="cursor-pointer"
            onClick={() =>
              void navigate({
                to: "/students/$studentId",
                params: { studentId: String(student.id) },
              })
            }
          >
            <TableCell>{student.username}</TableCell>
            <TableCell>{student.name}</TableCell>
            <TableCell>{student.major ?? "—"}</TableCell>
            <TableCell>{student.success_count}</TableCell>
            <TableCell className="whitespace-nowrap">
              {formatDateTime(student.latest_submitted_at)}
            </TableCell>
            <TableCell title={latestCountsTitle(student)}>
              {student.latest_counts ? student.latest_counts.fail : "—"}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
