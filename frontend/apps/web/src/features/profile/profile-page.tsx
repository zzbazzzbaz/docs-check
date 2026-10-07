import { Badge } from "@repo/ui/components/badge";
import { Button } from "@repo/ui/components/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@repo/ui/components/card";
import { useSuspenseQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { meQueryOptions } from "@/features/auth/api";

const ROLE_LABELS: Record<string, string> = {
  student: "学生",
  teacher: "教师",
  admin: "管理员",
};

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[6rem_1fr] items-center gap-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span>{value}</span>
    </div>
  );
}

export function ProfilePage() {
  const { data: me } = useSuspenseQuery(meQueryOptions);
  const isStudent = me.role === "student";

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">个人信息</h1>
        <Button asChild variant="outline" size="sm">
          <Link to="/change-password">修改密码</Link>
        </Button>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            {me.name || me.username}
            <Badge variant="secondary">{ROLE_LABELS[me.role] ?? me.role}</Badge>
            {me.must_change_password && <Badge variant="destructive">需修改初始密码</Badge>}
          </CardTitle>
          <CardDescription>账号 {me.username}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Field label="姓名" value={me.name || "—"} />
          {isStudent && <Field label="专业" value={me.major ?? "—"} />}
          {isStudent && <Field label="指导教师" value={me.teacher?.name ?? "未分配"} />}
          <Field label="状态" value={me.must_change_password ? "待修改初始密码" : "正常"} />
        </CardContent>
      </Card>
    </div>
  );
}
