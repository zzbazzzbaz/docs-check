import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "@repo/ui/components/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@repo/ui/components/card";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@repo/ui/components/form";
import { Input } from "@repo/ui/components/input";
import { useMutation, useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { changePassword, meQueryOptions } from "@/features/auth/api";

const changePasswordSchema = z
  .object({
    oldPassword: z.string().min(1, "请输入旧密码"),
    newPassword: z.string().min(6, "新密码至少 6 位").max(128, "新密码最多 128 位"),
    confirmPassword: z.string().min(1, "请再次输入新密码"),
  })
  .refine((values) => values.newPassword === values.confirmPassword, {
    message: "两次输入的新密码不一致",
    path: ["confirmPassword"],
  })
  .refine((values) => values.newPassword !== values.oldPassword, {
    message: "新密码不能与旧密码相同",
    path: ["newPassword"],
  });

type ChangePasswordFormValues = z.infer<typeof changePasswordSchema>;

export function ChangePasswordPage() {
  const { data: me } = useSuspenseQuery(meQueryOptions);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const form = useForm<ChangePasswordFormValues>({
    resolver: zodResolver(changePasswordSchema),
    defaultValues: { oldPassword: "", newPassword: "", confirmPassword: "" },
  });

  const mutation = useMutation({
    mutationFn: (values: ChangePasswordFormValues) =>
      changePassword(values.oldPassword, values.newPassword),
    onSuccess: async () => {
      toast.success("密码已修改");
      await queryClient.invalidateQueries({ queryKey: ["me"] });
      await navigate({ to: "/" });
    },
  });

  return (
    <div className="mx-auto max-w-md p-6">
      <Card>
        <CardHeader>
          <CardTitle>修改密码</CardTitle>
          <CardDescription>
            {me.must_change_password
              ? "首次登录请先修改初始密码，之后才能使用系统功能。"
              : "修改成功后当前登录状态保持有效。"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form
              onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
              className="grid gap-4"
              noValidate
            >
              <FormField
                control={form.control}
                name="oldPassword"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>旧密码</FormLabel>
                    <FormControl>
                      <Input
                        type="password"
                        autoComplete="current-password"
                        placeholder={me.must_change_password ? "初始密码" : undefined}
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="newPassword"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>新密码</FormLabel>
                    <FormControl>
                      <Input type="password" autoComplete="new-password" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="confirmPassword"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>确认新密码</FormLabel>
                    <FormControl>
                      <Input type="password" autoComplete="new-password" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <Button type="submit" className="w-full" disabled={mutation.isPending}>
                {mutation.isPending ? "提交中…" : "确认修改"}
              </Button>
            </form>
          </Form>
        </CardContent>
      </Card>
    </div>
  );
}
