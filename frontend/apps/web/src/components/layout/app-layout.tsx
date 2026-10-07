import type { components } from "@repo/api-client";
import { Button } from "@repo/ui/components/button";
import { ThemeToggle } from "@repo/ui/components/theme-toggle";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { LogOut } from "lucide-react";
import type { ReactNode } from "react";

import { clearToken } from "@/features/auth/token";

type Me = components["schemas"]["MeResponse"];

interface NavItem {
  to: "/" | "/students" | "/profile";
  label: string;
  exact?: boolean;
}

/** 顶部导航按角色区分：学生「我的提交」，教师「我的学生」；个人信息共用。 */
const NAV_BY_ROLE: Record<string, NavItem[]> = {
  student: [
    { to: "/", label: "我的提交", exact: true },
    { to: "/profile", label: "个人信息" },
  ],
  teacher: [
    { to: "/students", label: "我的学生" },
    { to: "/profile", label: "个人信息" },
  ],
};

export function AppLayout({ me, children }: { me: Me; children: ReactNode }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const navItems = NAV_BY_ROLE[me.role] ?? [];

  function logout() {
    clearToken();
    queryClient.clear();
    void navigate({ to: "/login" });
  }

  return (
    <div className="flex min-h-svh flex-col">
      <header className="flex h-14 items-center justify-between border-b px-6">
        <div className="flex items-center gap-6">
          <span className="font-semibold">论文格式审核</span>
          <nav className="flex items-center gap-1">
            {navItems.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                activeOptions={{ exact: item.exact ?? false }}
                activeProps={{ className: "bg-accent text-accent-foreground" }}
                inactiveProps={{ className: "text-muted-foreground hover:text-foreground" }}
                className="rounded-md px-3 py-1.5 text-sm font-medium transition-colors"
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-1">
          <span className="mr-1 text-sm text-muted-foreground">{me.name || me.username}</span>
          <ThemeToggle />
          <Button variant="ghost" size="icon" onClick={logout} aria-label="退出登录">
            <LogOut />
          </Button>
        </div>
      </header>
      <main className="flex-1">{children}</main>
    </div>
  );
}
