import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "@repo/ui/components/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@repo/ui/components/dialog";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@repo/ui/components/form";
import { Input } from "@repo/ui/components/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@repo/ui/components/select";
import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import {
  type AdminUserItem,
  type AdminUserRole,
  teacherOptionsQueryOptions,
  useCreateUserMutation,
  useUpdateUserMutation,
} from "../api";

const formSchema = z.object({
  username: z.string().min(3, "账号至少 3 位").max(32, "账号最多 32 位"),
  name: z.string().min(1, "请输入姓名").max(64, "姓名最多 64 位"),
  major: z.string().max(64, "专业最多 64 位"),
  teacherId: z.string(),
});

type FormValues = z.infer<typeof formSchema>;

/** Select 的「未分配」哨兵值（后端用 teacher_id: null 表示）。 */
const NONE_TEACHER = "none";

interface UserFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  role: AdminUserRole;
  /** null = 新建；否则为编辑对象。 */
  user: AdminUserItem | null;
}

export function UserFormDialog({ open, onOpenChange, role, user }: UserFormDialogProps) {
  const isEdit = user !== null;
  const createUser = useCreateUserMutation();
  const updateUser = useUpdateUserMutation();
  const teachers = useQuery({
    ...teacherOptionsQueryOptions(""),
    enabled: open && role === "student",
  });

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: { username: "", name: "", major: "", teacherId: NONE_TEACHER },
  });

  // 每次打开按当前对象重置表单
  useEffect(() => {
    if (!open) {
      return;
    }
    form.reset({
      username: user?.username ?? "",
      name: user?.name ?? "",
      major: user?.major ?? "",
      teacherId: user?.teacher ? String(user.teacher.id) : NONE_TEACHER,
    });
  }, [open, user, form]);

  function onSubmit(values: FormValues) {
    const teacherId = values.teacherId === NONE_TEACHER ? null : Number(values.teacherId);
    const close = { onSuccess: () => onOpenChange(false) };

    if (isEdit && user) {
      updateUser.mutate(
        role === "student"
          ? {
              userId: user.id,
              input: { name: values.name, major: values.major || null, teacher_id: teacherId },
            }
          : { userId: user.id, input: { name: values.name } },
        close,
      );
      return;
    }

    createUser.mutate(
      role === "student"
        ? {
            role,
            username: values.username,
            name: values.name,
            major: values.major || null,
            teacher_id: teacherId,
          }
        : { role, username: values.username, name: values.name },
      close,
    );
  }

  const pending = createUser.isPending || updateUser.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? "编辑" : "新建"}
            {role === "student" ? "学生" : "教师"}
          </DialogTitle>
          <DialogDescription>
            {isEdit ? "账号与角色不可修改。" : "初始密码 123456，首次登录需修改密码。"}
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="grid gap-4" noValidate>
            {!isEdit && (
              <FormField
                control={form.control}
                name="username"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{role === "student" ? "学号" : "工号"}</FormLabel>
                    <FormControl>
                      <Input autoComplete="off" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>姓名</FormLabel>
                  <FormControl>
                    <Input autoComplete="off" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            {role === "student" && (
              <>
                <FormField
                  control={form.control}
                  name="major"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>专业（可空）</FormLabel>
                      <FormControl>
                        <Input autoComplete="off" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="teacherId"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>指导教师（可空）</FormLabel>
                      <Select value={field.value} onValueChange={field.onChange}>
                        <FormControl>
                          <SelectTrigger className="w-full">
                            <SelectValue placeholder="未分配" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value={NONE_TEACHER}>未分配</SelectItem>
                          {(teachers.data ?? []).map((teacher) => (
                            <SelectItem key={teacher.id} value={String(teacher.id)}>
                              {teacher.name}（{teacher.username}）
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </>
            )}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                取消
              </Button>
              <Button type="submit" disabled={pending}>
                {pending ? "提交中…" : "保存"}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
