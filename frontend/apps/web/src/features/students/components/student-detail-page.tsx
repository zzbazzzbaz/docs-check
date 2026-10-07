import { Button } from "@repo/ui/components/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@repo/ui/components/card";
import { Skeleton } from "@repo/ui/components/skeleton";
import { useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import { useState } from "react";

import { PaginationFooter } from "@/components/pagination-footer";
import { meQueryOptions } from "@/features/auth/api";
import { SubmissionsTable } from "@/features/submissions/components/submissions-table";
import { toErrorMessage } from "@/lib/api";
import { studentQueryOptions, studentSubmissionsQueryOptions } from "../api";

const PAGE_SIZE = 20;

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[6rem_1fr] items-center gap-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span>{value}</span>
    </div>
  );
}

export function StudentDetailPage({ studentId }: { studentId: number }) {
  const { data: me } = useSuspenseQuery(meQueryOptions);
  const [offset, setOffset] = useState(0);

  const student = useQuery(studentQueryOptions(studentId));
  const submissions = useQuery(studentSubmissionsQueryOptions(studentId, offset, PAGE_SIZE));

  const backLink = (
    <Button asChild variant="ghost" size="sm">
      <Link to="/students">
        <ArrowLeft />
        返回我的学生
      </Link>
    </Button>
  );

  if (student.isLoading) {
    return (
      <div className="mx-auto max-w-4xl space-y-6 p-6">
        {backLink}
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (student.isError || !student.data) {
    return (
      <div className="mx-auto max-w-4xl space-y-4 p-6">
        <p className="text-sm text-destructive">{toErrorMessage(student.error, "加载失败")}</p>
        {backLink}
      </div>
    );
  }

  const items = submissions.data?.items ?? [];
  const total = submissions.data?.total ?? 0;

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <div className="flex items-center gap-3">
        {backLink}
        <h1 className="text-xl font-semibold">学生详情</h1>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{student.data.name}</CardTitle>
          <CardDescription>学号 {student.data.username}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Field label="姓名" value={student.data.name} />
          <Field label="学号" value={student.data.username} />
          <Field label="专业" value={student.data.major ?? "—"} />
          <Field label="指导教师" value={me.name || me.username} />
        </CardContent>
      </Card>

      <div className="space-y-4">
        <h2 className="font-semibold">提交记录</h2>

        {submissions.isLoading ? (
          <Skeleton className="h-48 w-full" />
        ) : submissions.isError ? (
          <p className="text-sm text-destructive">
            {toErrorMessage(submissions.error, "加载失败")}
          </p>
        ) : items.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center text-sm text-muted-foreground">
              该学生还没有提交记录
            </CardContent>
          </Card>
        ) : (
          <div className="overflow-hidden rounded-lg border">
            <SubmissionsTable items={items} />
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
      </div>
    </div>
  );
}
