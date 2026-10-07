import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";

/** 教师区守卫：非教师（学生/管理员）统一回到首页，由首页再分流。 */
export const Route = createFileRoute("/_auth/_teacher")({
  beforeLoad: ({ context }) => {
    if (context.me.role !== "teacher") {
      throw redirect({ to: "/" });
    }
  },
  component: Outlet,
});
