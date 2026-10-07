import { Button } from "@repo/ui/components/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@repo/ui/components/card";
import { Skeleton } from "@repo/ui/components/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@repo/ui/components/table";
import { useMutation, useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import { toast } from "sonner";

import { meQueryOptions } from "@/features/auth/api";
import { toErrorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { downloadSubmissionFile, submissionQueryOptions } from "../api";
import { COUNT_FIELDS, COUNT_LABELS, orderedScopes, totalCount } from "../lib/status";
import { StatusBadge } from "./status-badge";

export function SubmissionDetailPage({ submissionId }: { submissionId: number }) {
  const { data: me } = useSuspenseQuery(meQueryOptions);
  const { data, isLoading, isError, error } = useQuery(submissionQueryOptions(submissionId));
  const backTo = me.role === "teacher" ? "/students" : "/";

  const download = useMutation({
    mutationFn: (kind: "original" | "marked") =>
      downloadSubmissionFile(
        submissionId,
        kind,
        data?.original_filename ?? `submission-${submissionId}.docx`,
      ),
    onError: (err) => toast.error(toErrorMessage(err, "下载失败")),
  });

  if (isLoading) {
    return (
      <div className="mx-auto max-w-4xl p-6">
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="mx-auto max-w-4xl space-y-4 p-6">
        <p className="text-sm text-destructive">{toErrorMessage(error, "加载失败")}</p>
        <Button asChild variant="outline" size="sm">
          <Link to={backTo}>返回列表</Link>
        </Button>
      </div>
    );
  }

  if (!data) {
    return null;
  }

  const counts = data.counts;
  const success = data.status === "success";
  const pendingLike = data.status === "pending" || data.status === "processing";
  const byScope = data.by_scope ?? {};
  const scopeList = orderedScopes(byScope);

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <div className="flex items-center gap-3">
        <Button asChild variant="ghost" size="sm">
          <Link to={backTo}>
            <ArrowLeft />
            返回
          </Link>
        </Button>
        <h1 className="text-xl font-semibold">提交详情</h1>
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center gap-3">
            <StatusBadge status={data.status} counts={counts} />
            <CardTitle className="text-base">第 {data.sequence} 次提交</CardTitle>
          </div>
          <CardDescription className="break-all">{data.original_filename}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <div className="grid gap-2 sm:grid-cols-2">
            <div>
              <span className="text-muted-foreground">提交时间：</span>
              {formatDateTime(data.created_at)}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={data.status === "failed" || download.isPending}
              onClick={() => download.mutate("original")}
            >
              下载原始 word
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={!success || download.isPending}
              onClick={() => download.mutate("marked")}
            >
              下载标注 word
            </Button>
          </div>
        </CardContent>
      </Card>

      {pendingLike && (
        <Card>
          <CardContent className="py-6 text-sm text-muted-foreground">
            {data.status === "pending" ? "已排队，等待审核。" : "审核中，页面会自动刷新。"}
          </CardContent>
        </Card>
      )}

      {data.status === "failed" && (
        <Card className="border-destructive/50">
          <CardHeader>
            <CardTitle className="text-base text-destructive">审核失败</CardTitle>
            <CardDescription className="whitespace-pre-wrap">
              {data.error_message ?? "文档无法解析"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild variant="outline" size="sm">
              <Link to={backTo}>返回列表重新上传</Link>
            </Button>
          </CardContent>
        </Card>
      )}

      {success &&
        (totalCount(counts) === 0 ? (
          <Card>
            <CardContent className="py-12 text-center text-sm text-muted-foreground">
              未发现问题
            </CardContent>
          </Card>
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {COUNT_FIELDS.map((field) => (
                <Card key={field}>
                  <CardHeader>
                    <CardDescription>{COUNT_LABELS[field]}</CardDescription>
                    <CardTitle className="text-2xl">{counts[field]}</CardTitle>
                  </CardHeader>
                </Card>
              ))}
            </div>

            {scopeList.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">按模块统计</CardTitle>
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>模块</TableHead>
                        {COUNT_FIELDS.map((field) => (
                          <TableHead key={field} className="text-right">
                            {COUNT_LABELS[field]}
                          </TableHead>
                        ))}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {scopeList.map((scope) => (
                        <TableRow key={scope}>
                          <TableCell>{scope}</TableCell>
                          {COUNT_FIELDS.map((field) => (
                            <TableCell key={field} className="text-right">
                              {byScope[scope][field]}
                            </TableCell>
                          ))}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            )}
          </>
        ))}
    </div>
  );
}
