import { Button } from "@repo/ui/components/button";
import { Input } from "@repo/ui/components/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@repo/ui/components/select";
import { Skeleton } from "@repo/ui/components/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@repo/ui/components/tabs";
import { useDebouncedValue } from "@repo/ui/hooks/use-debounced-value";
import { useQuery } from "@tanstack/react-query";
import { Plus, Search } from "lucide-react";
import { useState } from "react";

import { PaginationFooter } from "@/components/pagination-footer";
import { toErrorMessage } from "@/lib/api";
import {
  type AdminUserItem,
  type AdminUserRole,
  adminUsersQueryOptions,
  useResetPasswordMutation,
  useSetUserStatusMutation,
} from "../api";
import { ConfirmDialog } from "./confirm-dialog";
import { UserFormDialog } from "./user-form-dialog";
import { UsersTable } from "./users-table";

const PAGE_SIZE = 10;

type StatusFilter = "all" | "active" | "inactive";

interface ConfirmTarget {
  action: "status" | "reset";
  user: AdminUserItem;
}

export function UsersPage({ initialRole = "student" }: { initialRole?: AdminUserRole }) {
  const [role, setRole] = useState<AdminUserRole>(initialRole);
  const [keyword, setKeyword] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [offset, setOffset] = useState(0);
  const [formOpen, setFormOpen] = useState(false);
  const [formTarget, setFormTarget] = useState<AdminUserItem | null>(null);
  const [confirmTarget, setConfirmTarget] = useState<ConfirmTarget | null>(null);

  const q = useDebouncedValue(keyword.trim(), 300);
  const isActive = status === "all" ? undefined : status === "active";
  const { data, isLoading, isError, error } = useQuery(
    adminUsersQueryOptions({ role, isActive, q, offset, limit: PAGE_SIZE }),
  );

  const setStatusMutation = useSetUserStatusMutation();
  const resetMutation = useResetPasswordMutation();

  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  function openCreate() {
    setFormTarget(null);
    setFormOpen(true);
  }

  function openEdit(user: AdminUserItem) {
    setFormTarget(user);
    setFormOpen(true);
  }

  function confirmDescription(target: ConfirmTarget): string {
    if (target.action === "reset") {
      return `将把「${target.user.name}」的密码重置为初始密码 123456，并要求下次登录修改密码。`;
    }
    if (target.user.is_active) {
      const students =
        target.user.role === "teacher" && target.user.student_count > 0
          ? `\n该教师名下还有 ${target.user.student_count} 名学生，请及时重新分配。`
          : "";
      return `禁用后「${target.user.name}」将无法登录，数据保留，可随时启用。${students}`;
    }
    return `启用后「${target.user.name}」可以正常登录。`;
  }

  function runConfirm() {
    if (!confirmTarget) {
      return;
    }
    const { action, user } = confirmTarget;
    if (action === "reset") {
      resetMutation.mutate(user.id, { onSuccess: () => setConfirmTarget(null) });
    } else {
      setStatusMutation.mutate(
        { userId: user.id, isActive: !user.is_active },
        { onSuccess: () => setConfirmTarget(null) },
      );
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">用户管理</h1>
        <Button onClick={openCreate}>
          <Plus />
          新建{role === "student" ? "学生" : "教师"}
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Tabs
          value={role}
          onValueChange={(value) => {
            setRole(value as AdminUserRole);
            setOffset(0);
          }}
        >
          <TabsList>
            <TabsTrigger value="student">学生</TabsTrigger>
            <TabsTrigger value="teacher">教师</TabsTrigger>
          </TabsList>
        </Tabs>
        <div className="relative">
          <Search className="absolute top-1/2 left-2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            className="w-64 pl-8"
            placeholder="搜索账号 / 姓名"
            value={keyword}
            onChange={(event) => {
              setKeyword(event.target.value);
              setOffset(0);
            }}
          />
        </div>
        <Select
          value={status}
          onValueChange={(value) => {
            setStatus(value as StatusFilter);
            setOffset(0);
          }}
        >
          <SelectTrigger className="w-32">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部状态</SelectItem>
            <SelectItem value="active">启用</SelectItem>
            <SelectItem value="inactive">禁用</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : isError ? (
        <p className="text-sm text-destructive">{toErrorMessage(error, "加载失败")}</p>
      ) : items.length === 0 ? (
        <div className="rounded-lg border py-16 text-center text-sm text-muted-foreground">
          {q ? "没有找到匹配的账号" : `暂无${role === "student" ? "学生" : "教师"}账号`}
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border">
          <UsersTable
            role={role}
            items={items}
            onEdit={openEdit}
            onToggleStatus={(user) => setConfirmTarget({ action: "status", user })}
            onResetPassword={(user) => setConfirmTarget({ action: "reset", user })}
          />
        </div>
      )}

      {items.length > 0 && (
        <PaginationFooter
          offset={offset}
          limit={PAGE_SIZE}
          total={total}
          onOffsetChange={setOffset}
        />
      )}

      <UserFormDialog open={formOpen} onOpenChange={setFormOpen} role={role} user={formTarget} />
      <ConfirmDialog
        open={confirmTarget !== null}
        onOpenChange={(open) => {
          if (!open) {
            setConfirmTarget(null);
          }
        }}
        title={
          confirmTarget?.action === "reset"
            ? "重置密码"
            : confirmTarget?.user.is_active
              ? "禁用账号"
              : "启用账号"
        }
        description={confirmTarget ? confirmDescription(confirmTarget) : ""}
        confirmText={
          confirmTarget?.action === "reset"
            ? "重置"
            : confirmTarget?.user.is_active
              ? "禁用"
              : "启用"
        }
        destructive={confirmTarget?.action === "reset" || confirmTarget?.user.is_active === true}
        onConfirm={runConfirm}
      />
    </div>
  );
}
