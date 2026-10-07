import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";

import { AppLayout } from "@/components/layout/app-layout";
import { meQueryOptions } from "@/features/auth/api";
import { getToken } from "@/features/auth/token";

export const Route = createFileRoute("/_auth")({
  beforeLoad: async ({ context, location }) => {
    if (!getToken()) {
      throw redirect({ to: "/login" });
    }
    const me = await context.queryClient.ensureQueryData(meQueryOptions);
    // 强制改密门禁：未改初始密码前只能停留在修改密码页
    if (me.must_change_password && location.pathname !== "/change-password") {
      throw redirect({ to: "/change-password" });
    }
    return { me };
  },
  component: AuthLayout,
});

function AuthLayout() {
  const { me } = Route.useRouteContext();

  return (
    <AppLayout me={me}>
      <Outlet />
    </AppLayout>
  );
}
