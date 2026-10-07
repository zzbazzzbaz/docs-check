import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@repo/ui/components/card";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { toErrorMessage } from "@/lib/api";
import { adminStatsQueryOptions } from "./api";

export function DashboardPage() {
  const { data, isLoading, isError, error } = useQuery(adminStatsQueryOptions);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">仪表盘</h1>
        <p className="text-sm text-muted-foreground">账号与提交数量概览（不含提交内容）。</p>
      </div>

      {isError ? (
        <p className="text-sm text-destructive">{toErrorMessage(error, "加载失败")}</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Card>
            <CardHeader>
              <CardDescription>学生数（启用）</CardDescription>
              <CardTitle className="text-2xl">{isLoading ? "—" : data?.student_count}</CardTitle>
            </CardHeader>
            <CardContent>
              <Link
                to="/users"
                search={{ role: "student" }}
                className="text-sm underline underline-offset-4"
              >
                前往学生管理
              </Link>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardDescription>教师数（启用）</CardDescription>
              <CardTitle className="text-2xl">{isLoading ? "—" : data?.teacher_count}</CardTitle>
            </CardHeader>
            <CardContent>
              <Link
                to="/users"
                search={{ role: "teacher" }}
                className="text-sm underline underline-offset-4"
              >
                前往教师管理
              </Link>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardDescription>提交数（全部）</CardDescription>
              <CardTitle className="text-2xl">{isLoading ? "—" : data?.submission_count}</CardTitle>
            </CardHeader>
            <CardContent>
              <span className="text-sm text-muted-foreground">仅计数，不展示提交内容</span>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
