import { Badge } from "@repo/ui/components/badge";
import { Button } from "@repo/ui/components/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@repo/ui/components/dropdown-menu";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@repo/ui/components/table";
import { MoreHorizontal } from "lucide-react";

import { formatDateTime } from "@/lib/format";
import type { AdminUserItem, AdminUserRole } from "../api";

interface UsersTableProps {
  role: AdminUserRole;
  items: AdminUserItem[];
  onEdit: (user: AdminUserItem) => void;
  onToggleStatus: (user: AdminUserItem) => void;
  onResetPassword: (user: AdminUserItem) => void;
}

/** 管理端用户表格：列随角色页签切换。 */
export function UsersTable({
  role,
  items,
  onEdit,
  onToggleStatus,
  onResetPassword,
}: UsersTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{role === "student" ? "学号" : "工号"}</TableHead>
          <TableHead>姓名</TableHead>
          {role === "student" ? (
            <>
              <TableHead>专业</TableHead>
              <TableHead>指导教师</TableHead>
            </>
          ) : (
            <TableHead>名下学生数</TableHead>
          )}
          <TableHead>状态</TableHead>
          <TableHead>创建时间</TableHead>
          <TableHead className="w-16 text-right">操作</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((user) => (
          <TableRow key={user.id}>
            <TableCell>{user.username}</TableCell>
            <TableCell>{user.name}</TableCell>
            {role === "student" ? (
              <>
                <TableCell>{user.major ?? "—"}</TableCell>
                <TableCell>{user.teacher?.name ?? "未分配"}</TableCell>
              </>
            ) : (
              <TableCell>{user.student_count}</TableCell>
            )}
            <TableCell>
              <Badge variant={user.is_active ? "default" : "secondary"}>
                {user.is_active ? "启用" : "禁用"}
              </Badge>
            </TableCell>
            <TableCell className="whitespace-nowrap">{formatDateTime(user.created_at)}</TableCell>
            <TableCell className="text-right">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon" aria-label="操作">
                    <MoreHorizontal />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={() => onEdit(user)}>编辑</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => onResetPassword(user)}>
                    重置密码
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => onToggleStatus(user)}>
                    {user.is_active ? "禁用" : "启用"}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
