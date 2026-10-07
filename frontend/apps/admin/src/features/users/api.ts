import type { components } from "@repo/api-client";
import { queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, unwrap } from "@/lib/api";

export type AdminUserRole = "student" | "teacher";
export type AdminUserItem = components["schemas"]["AdminUserItem"];

export interface AdminUsersQuery {
  role: AdminUserRole;
  isActive: boolean | undefined;
  q: string;
  offset: number;
  limit: number;
}

export const adminUsersQueryOptions = (query: AdminUsersQuery) =>
  queryOptions({
    queryKey: ["admin-users", query],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/admin/users", {
          params: {
            query: {
              role: query.role,
              is_active: query.isActive,
              q: query.q || undefined,
              offset: query.offset,
              limit: query.limit,
            },
          },
        }),
      ),
  });

export const teacherOptionsQueryOptions = (q: string) =>
  queryOptions({
    queryKey: ["teacher-options", q],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/admin/teachers/options", { params: { query: { q: q || undefined } } }),
      ),
  });

export interface CreateUserInput {
  role: AdminUserRole;
  username: string;
  name: string;
  major?: string | null;
  teacher_id?: number | null;
}

export interface UpdateUserInput {
  name?: string;
  major?: string | null;
  teacher_id?: number | null;
}

export function useCreateUserMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateUserInput) =>
      unwrap(api.POST("/api/v1/admin/users", { body: input })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin-users"] });
      void queryClient.invalidateQueries({ queryKey: ["admin-stats"] });
      toast.success("账号已创建，初始密码 123456");
    },
  });
}

export function useUpdateUserMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ userId, input }: { userId: number; input: UpdateUserInput }) =>
      unwrap(
        api.PATCH("/api/v1/admin/users/{user_id}", {
          params: { path: { user_id: userId } },
          body: input,
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin-users"] });
      toast.success("已保存");
    },
  });
}

export function useSetUserStatusMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ userId, isActive }: { userId: number; isActive: boolean }) =>
      unwrap(
        api.PATCH("/api/v1/admin/users/{user_id}/status", {
          params: { path: { user_id: userId } },
          body: { is_active: isActive },
        }),
      ),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: ["admin-users"] });
      void queryClient.invalidateQueries({ queryKey: ["admin-stats"] });
      toast.success(variables.isActive ? "已启用" : "已禁用");
    },
  });
}

export function useResetPasswordMutation() {
  return useMutation({
    mutationFn: (userId: number) =>
      unwrap(
        api.POST("/api/v1/admin/users/{user_id}/reset-password", {
          params: { path: { user_id: userId } },
        }),
      ),
    onSuccess: () => toast.success("已重置为初始密码 123456"),
  });
}
